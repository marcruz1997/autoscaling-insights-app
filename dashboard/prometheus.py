"""Consultas ao Thanos Querier do OpenShift (API compatível com Prometheus)."""
import math
from concurrent.futures import ThreadPoolExecutor

from httpclient import ApiError

_pool = ThreadPoolExecutor(max_workers=16)


def _value(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


class Prometheus:
    def __init__(self, http, url):
        self.http = http
        self.url = url.rstrip("/")

    def _get(self, path, params):
        data = self.http.get_json(self.url + path, params=params)
        if data.get("status") != "success":
            raise ApiError("thanos: " + str(data.get("error", "erro desconhecido")))
        return data["data"]["result"]

    def query(self, q):
        """Consulta instantânea -> lista de (rótulos, valor)."""
        out = []
        for r in self._get("/api/v1/query", {"query": q}):
            v = _value(r["value"][1])
            if v is not None:
                out.append((r["metric"], v))
        return out

    def query_range(self, q, label, start, end, step):
        """Consulta de intervalo -> [{"name": rótulo, "points": [[ms, valor], ...]}]."""
        params = {"query": q, "start": int(start), "end": int(end), "step": int(step)}
        out = []
        for r in self._get("/api/v1/query_range", params):
            points = []
            for ts, raw in r["values"]:
                v = _value(raw)
                if v is not None:
                    points.append([ts * 1000, round(v, 2)])
            out.append({"name": r["metric"].get(label) or "total", "points": points})
        return out

    # ---------- várias consultas em paralelo ----------

    def query_many(self, queries, errors):
        """{chave: promql} -> {chave: resultado}; falhas vão para errors[chave]."""
        futures = {k: _pool.submit(self.query, q) for k, q in queries.items()}
        return self._collect(futures, errors, [])

    def range_many(self, queries, label, start, end, step, errors):
        futures = {k: _pool.submit(self.query_range, q, label, start, end, step) for k, q in queries.items()}
        return self._collect(futures, errors, [])

    @staticmethod
    def _collect(futures, errors, default):
        out = {}
        for key, fut in futures.items():
            try:
                out[key] = fut.result()
            except Exception as exc:  # noqa: BLE001 - erro parcial vira aviso no painel
                errors[key] = str(exc)
                out[key] = default
        return out


def index(samples, *labels):
    """Indexa amostras por um ou mais rótulos unidos por "/"."""
    return {"/".join(m.get(l, "") for l in labels): v for m, v in samples}


def pick(idx, key):
    v = idx.get(key)
    return None if v is None else round(v, 1)
