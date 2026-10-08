"""Histórico das recomendações do VPA.

O OpenShift não exporta as recomendações para o Prometheus, então o painel grava a
cada minuto num arquivo JSON Lines no volume do painel. Só grava quando a
recomendação muda ou, no mínimo, uma vez a cada 15 minutos.
"""
import bisect
import json
import logging
import os
import threading
import time

log = logging.getLogger("historico")

HEARTBEAT_MS = 15 * 60 * 1000


class HistoryStore:
    def __init__(self, data_dir, retain_days):
        self.retain_ms = retain_days * 24 * 3600 * 1000
        self.lock = threading.Lock()
        self.data = {}  # "ns/deployment/container" -> [registro, ...] em ordem de tempo
        self.path = None
        try:
            os.makedirs(data_dir, exist_ok=True)
            path = os.path.join(data_dir, "vpa-history.jsonl")
            open(path, "a").close()
            self.path = path
        except OSError:
            log.warning("%s não é gravável; histórico só em memória (perde ao reiniciar)", data_dir)
            return
        self._load()

    @property
    def persistent(self):
        return self.path is not None

    def describe(self):
        return self.path or "memória"

    # ---------- arquivo ----------

    def _load(self):
        cutoff = _now_ms() - self.retain_ms
        count = 0
        with open(self.path) as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                key = e.pop("k", None)
                if not key or e.get("t", 0) < cutoff:
                    continue
                self.data.setdefault(key, []).append(e)
                count += 1
        for entries in self.data.values():
            entries.sort(key=lambda e: e["t"])
        log.info("%d registros carregados de %s", count, self.path)
        self._rewrite()

    def _rewrite(self):
        """Regrava o arquivo só com o que está dentro da retenção."""
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            for key, entries in self.data.items():
                for e in entries:
                    fh.write(json.dumps({**e, "k": key}) + "\n")
        os.replace(tmp, self.path)

    # ---------- gravação ----------

    def record(self, vpas):
        now = _now_ms()
        new_lines = []
        with self.lock:
            for v in vpas:
                if v["targetKind"] != "Deployment":
                    continue
                for c in v["containers"]:
                    if not c["target"]:
                        continue
                    key = f'{v["namespace"]}/{v["targetName"]}/{c["name"]}'
                    entry = {"t": now, "m": v["updateMode"], "tg": c["target"], "lo": c["lowerBound"],
                             "up": c["upperBound"], "un": c["uncappedTarget"]}
                    entries = self.data.setdefault(key, [])
                    if entries:
                        last = entries[-1]
                        same = all(last.get(k) == entry[k] for k in ("m", "tg", "lo", "up", "un"))
                        if same and now - last["t"] < HEARTBEAT_MS:
                            continue
                    entries.append(entry)
                    new_lines.append({**entry, "k": key})

            # descarta o que passou da retenção
            cutoff = now - self.retain_ms
            trimmed = False
            for key in list(self.data):
                entries = self.data[key]
                i = bisect.bisect_left([e["t"] for e in entries], cutoff)
                if i:
                    self.data[key] = entries[i:]
                    trimmed = True
                if not self.data[key]:
                    del self.data[key]

            if not self.path:
                return
            try:
                if trimmed:
                    self._rewrite()
                elif new_lines:
                    with open(self.path, "a") as fh:
                        for e in new_lines:
                            fh.write(json.dumps(e) + "\n")
            except OSError as exc:
                log.error("erro ao gravar o histórico: %s", exc)

    # ---------- leitura ----------

    def get(self, key, from_ms):
        """Registros da janela, mais o último anterior a ela (para a linha começar no início)."""
        with self.lock:
            entries = self.data.get(key, [])
            i = bisect.bisect_left([e["t"] for e in entries], from_ms)
            return [dict(e) for e in entries[max(0, i - 1):]]

    def first(self, key):
        with self.lock:
            entries = self.data.get(key)
            return entries[0]["t"] if entries else 0


def start_collector(store, kube, interval_s):
    """Thread que grava as recomendações a cada intervalo."""
    def loop():
        while True:
            try:
                store.record(kube.list_vpas())
            except Exception as exc:  # noqa: BLE001 - VPA ausente ou API fora: tenta de novo depois
                log.debug("coleta do histórico falhou: %s", exc)
            time.sleep(interval_s)

    t = threading.Thread(target=loop, name="coletor-historico", daemon=True)
    t.start()
    return t


def _now_ms():
    return int(time.time() * 1000)
