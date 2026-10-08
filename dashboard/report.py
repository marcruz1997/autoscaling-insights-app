"""Relatório executivo do Autoscaling Insights em HTML (abre no navegador e salva em PDF).

Recebe os dados já coletados pelas APIs do painel e devolve uma página única, sem
dependências externas: CSS embutido e gráficos em SVG gerados aqui. Cada marca dos
gráficos tem um <title>, que o navegador mostra ao passar o mouse.

Cores: paleta categórica do painel, validada para daltonismo (azul #2a78d6 = request
atual, laranja #eb6834 = VPA, roxo #4a3aa7 = uso). Status sempre com ícone + texto.
"""
from datetime import datetime, timedelta, timezone
from html import escape

BLUE, ORANGE, PURPLE = "#2a78d6", "#eb6834", "#4a3aa7"
ORANGE_SOFT = "#fbe1d6"
GRID, AXIS, INK, INK2, MUTED = "#e4e4e1", "#c7c7c2", "#1f1f1e", "#4d4d4b", "#6f6f6c"

STATUS = {  # rótulo -> (classe, ícone)
    "ok": ("st-ok", "✓"), "warn": ("st-warn", "!"), "bad": ("st-bad", "✕"), "info": ("st-info", "i"), "wait": ("st-wait", "…"),
}


# ---------------------------------------------------------------- formatação

def e(v):
    return escape("" if v is None else str(v))


def nf(v, d=0):
    if v is None:
        return "–"
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def f_cpu(m):
    if m is None:
        return "–"
    return f"{nf(m / 1000, 2)} cores" if abs(m) >= 1000 else f"{nf(m)}m"


def f_mem(mi):
    if mi is None:
        return "–"
    return f"{nf(mi / 1024, 2)} Gi" if abs(mi) >= 1024 else f"{nf(mi)} Mi"


def signed(v, f):
    if v is None:
        return "–"
    return ("+" if v > 0 else "−" if v < 0 else "") + f(abs(v))


def trunc(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def lab_text(x, y, name, n):
    """Rótulo de linha à esquerda do gráfico, truncado (o nome completo fica no hover)."""
    return f'<text x="{x}" y="{y:.1f}" class="lab" text-anchor="end"><title>{e(name)}</title>{e(trunc(name, n))}</text>'


def pill(text, kind):
    cls, icon = STATUS[kind]
    return f'<span class="pill {cls}"><span class="pi" aria-hidden="true">{icon}</span>{e(text)}</span>'


class Clock:
    """Converte horários ISO/epoch para o fuso do navegador de quem gerou o relatório."""

    def __init__(self, tz_offset_min):
        self.tz = timezone(timedelta(minutes=-tz_offset_min))
        off = -tz_offset_min
        self.label = "UTC" + (f"{'+' if off >= 0 else '−'}{abs(off) // 60:02d}:{abs(off) % 60:02d}" if off else "")

    def iso(self, s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(self.tz)
        except ValueError:
            return None

    def ms(self, t):
        return datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(self.tz)

    def fmt(self, dt, seconds=False):
        return dt.strftime("%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M") if dt else "–"


def ago(dt, now):
    if not dt:
        return "–"
    s = max(0, int((now - dt).total_seconds()))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return f"há {d}d {h}h" if d else f"há {h}h {m}m" if h else f"há {m}m"


# ---------------------------------------------------------------- regras (as mesmas do painel)

def res_status(req, rec, k):
    lo = rec and rec.get("lowerBound") and rec["lowerBound"].get(k)
    up = rec and rec.get("upperBound") and rec["upperBound"].get(k)
    if not rec or not rec.get("target"):
        return "Pending", "wait"
    if req is None:
        return "No request", "warn"
    if lo is not None and req < lo:
        return "Under-provisioned", "warn"
    if up is not None and req > up:
        return "Over-provisioned", "bad"
    return "Right-sized", "ok"


def hpa_state(h, now):
    conds = {c["type"]: c for c in h.get("conditions", [])}
    able, active, out = conds.get("AbleToScale"), conds.get("ScalingActive"), []
    if able and able["status"] == "False":
        out.append(("Unable to scale", "bad"))
    if active and active["status"] == "False":
        msg = active.get("message", "")
        since = None
        try:
            since = datetime.fromisoformat(active.get("since", "").replace("Z", "+00:00"))
        except ValueError:
            pass
        transient = any(x in msg.lower() for x in ("no metrics returned", "unable to get metrics", "did not receive metrics",
                                                    "unable to fetch metrics")) and "missing request" not in msg.lower()
        recent = since is not None and (now - since).total_seconds() < 300
        out.append(("Loading metrics", "info") if transient and recent else ("Metrics unavailable", "bad"))
    cur, mx, mn, des = h.get("currentReplicas") or 0, h.get("maxReplicas") or 0, h.get("minReplicas") or 0, h.get("desiredReplicas")
    if mx and cur >= mx:
        out.append(("At maxReplicas", "warn"))
    elif des and des != cur:
        out.append(("Scaling up" if des > cur else "Scaling down", "info"))
    elif cur <= mn and not out:
        out.append(("At minReplicas", "wait"))
    return out or [("Stable", "ok")]


def vpa_rel(rel):
    kind = (rel or {}).get("kind", "none")
    return {"conflict": ("VPA conflict", "bad"), "recommend": ("VPA recommendation only", "info"),
            "ok": ("VPA + custom metric", "ok")}.get(kind, ("Sem VPA", "wait"))


# ---------------------------------------------------------------- gráficos (SVG)

def svg_open(w, h, label):
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{e(label)}" '
            f'preserveAspectRatio="xMinYMin meet">')


def nice_max(v):
    if v <= 0:
        return 1
    import math
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * p:
            return m * p
    return 10 * p


def x_axis(x0, x1, y_top, y_bot, vmax, fmt, ticks=4):
    out = []
    for i in range(ticks + 1):
        v = vmax * i / ticks
        x = x0 + (x1 - x0) * i / ticks
        out.append(f'<line x1="{x:.1f}" y1="{y_top}" x2="{x:.1f}" y2="{y_bot}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{y_bot + 14}" class="tick" text-anchor="middle">{e(fmt(v))}</text>')
    return "".join(out)


def legend(items):
    return '<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{e(t)}</span>' for c, t in items) + "</div>"


def paired_bars(rows, fmt, a_name, b_name, a_color=BLUE, b_color=ORANGE, label_w=130, title="", W=540):
    """Barras horizontais agrupadas (2 séries, um eixo). rows = [(rótulo, a, b)]."""
    if not rows:
        return '<p class="empty">Sem dados.</p>'
    bar, gap, pad = 11, 2, 12
    row_h = bar * 2 + gap + pad
    x0, x1 = label_w, W - 64
    H = 18 + len(rows) * row_h + 22
    vmax = nice_max(max([max(a or 0, b or 0) for _, a, b in rows] + [1]))
    sx = lambda v: x0 + (x1 - x0) * (v or 0) / vmax
    out = [svg_open(W, H, title), x_axis(x0, x1, 8, H - 22, vmax, fmt)]
    y = 14
    for name, a, b in rows:
        out.append(lab_text(x0 - 10, y + bar + 4, name, 18))
        for i, (v, c, sname) in enumerate(((a, a_color, a_name), (b, b_color, b_name))):
            yy = y + i * (bar + gap)
            w = max(0, sx(v) - x0)
            out.append(f'<g><title>{e(name)} · {e(sname)}: {e(fmt(v))}</title>'
                       f'<rect x="{x0}" y="{yy}" width="{max(w, 0.5):.1f}" height="{bar}" rx="2" fill="{c}"/>'
                       f'<rect x="{x0}" y="{yy - 1}" width="{x1 - x0}" height="{bar + 2}" fill="transparent"/></g>')
            out.append(f'<text x="{x0 + w + 5:.1f}" y="{yy + bar - 2}" class="val">{e(fmt(v))}</text>')
        y += row_h
    out.append("</svg>")
    return legend([(a_color, a_name), (b_color, b_name)]) + "".join(out)


def request_vs_band(rows, title, W=540):
    """Request como % do target do VPA, com a faixa lower–upper. rows = [(rótulo, req, lo, tg, up, fmt)]."""
    rows = [r for r in rows if r[3]]
    if not rows:
        return '<p class="empty">Sem recomendações do VPA.</p>'
    row_h, label_w = 28, 170
    x0, x1 = label_w, W - 20
    H = 22 + len(rows) * row_h + 26
    pct = lambda v, t: None if v is None else v / t * 100
    vmax = min(400, nice_max(max([max(pct(r, t) or 0, pct(u, t) or 0) for _, r, _, t, u, _ in rows] + [150])))
    sx = lambda p: x0 + (x1 - x0) * min(max(p, 0), vmax) / vmax
    out = [svg_open(W, H, title), x_axis(x0, x1, 12, H - 26, vmax, lambda v: f"{nf(v)}%")]
    out.append(f'<line x1="{sx(100):.1f}" y1="12" x2="{sx(100):.1f}" y2="{H - 26}" stroke="{ORANGE}" stroke-width="2"/>')
    out.append(f'<text x="{sx(100):.1f}" y="6" class="tick" text-anchor="middle" fill="{ORANGE}">target</text>')
    y = 18
    for name, req, lo, tg, up, fmt in rows:
        cy = y + row_h / 2
        out.append(lab_text(x0 - 10, cy + 4, name, 24))
        if lo is not None and up is not None:
            out.append(f'<g><title>Faixa do VPA: {e(fmt(lo))} – {e(fmt(up))} (target {e(fmt(tg))})</title>'
                       f'<rect x="{sx(pct(lo, tg)):.1f}" y="{cy - 6:.1f}" width="{max(1, sx(pct(up, tg)) - sx(pct(lo, tg))):.1f}" '
                       f'height="12" rx="6" fill="{ORANGE_SOFT}"/></g>')
        if req is not None:
            p = pct(req, tg)
            clipped = p > vmax
            out.append(f'<g><title>{e(name)} · request {e(fmt(req))} = {nf(p)}% do target {e(fmt(tg))}</title>'
                       f'<circle cx="{sx(p):.1f}" cy="{cy:.1f}" r="5.5" fill="{BLUE}" stroke="#fff" stroke-width="2"/></g>')
            if clipped:
                out.append(f'<text x="{x1 - 8}" y="{cy - 8:.1f}" class="val" text-anchor="end">{nf(p)}% ›</text>')
        else:
            out.append(f'<text x="{x0 + 4}" y="{cy + 4:.1f}" class="val">sem request</text>')
        y += row_h
    out.append("</svg>")
    return legend([(BLUE, "Request atual"), (ORANGE_SOFT, "Faixa lower–upper do VPA"), (ORANGE, "Target (100%)")]) + "".join(out)


def history_chart(entries, k, fmt, clock, title):
    """Target do VPA ao longo do tempo (linha laranja) com a faixa lower–upper (área clara)."""
    pts = [x for x in entries if x.get("tg") and x["tg"].get(k) is not None]
    if len(pts) < 1:
        return '<p class="empty">Sem histórico.</p>'
    W, H, l, r, t, b = 270, 150, 62, 8, 10, 24
    t0, t1 = pts[0]["t"], max(pts[-1]["t"], pts[0]["t"] + 60000)
    vals = [v for x in pts for v in (x["tg"].get(k), (x.get("up") or {}).get(k)) if v is not None]
    vmax = nice_max(max(vals) * 1.05)
    sx = lambda tt: l + (W - l - r) * (tt - t0) / (t1 - t0)
    sy = lambda v: t + (H - t - b) * (1 - v / vmax)
    out = [svg_open(W, H, title)]
    for i in range(4):
        v = vmax * i / 3
        out.append(f'<line x1="{l}" y1="{sy(v):.1f}" x2="{W - r}" y2="{sy(v):.1f}" stroke="{GRID}"/>'
                   f'<text x="{l - 6}" y="{sy(v) + 3:.1f}" class="tick" text-anchor="end">{e(fmt(v))}</text>')
    for tt in (t0, t1):
        out.append(f'<text x="{sx(tt):.1f}" y="{H - 8}" class="tick" text-anchor="{"start" if tt == t0 else "end"}">'
                   f'{clock.ms(tt).strftime("%d/%m %H:%M")}</text>')

    def step_path(get):
        d, prev = [], None
        for x in pts:
            v = get(x)
            if v is None:
                continue
            X, Y = sx(x["t"]), sy(v)
            d.append(f"M{X:.1f},{Y:.1f}" if prev is None else f"H{X:.1f}V{Y:.1f}")
            prev = Y
        if prev is not None:
            d.append(f"H{sx(t1):.1f}")
        return "".join(d)
    # faixa: upper por cima, lower por baixo (degraus)
    up = [(x["t"], (x.get("up") or {}).get(k)) for x in pts]
    lo = [(x["t"], (x.get("lo") or {}).get(k)) for x in pts]
    if all(v is not None for _, v in up + lo):
        top, bot = [], []
        for i, (tt, v) in enumerate(up):
            nxt = up[i + 1][0] if i + 1 < len(up) else t1
            top += [(sx(tt), sy(v)), (sx(nxt), sy(v))]
        for i, (tt, v) in enumerate(lo):
            nxt = lo[i + 1][0] if i + 1 < len(lo) else t1
            bot += [(sx(tt), sy(v)), (sx(nxt), sy(v))]
        poly = " ".join(f"{a:.1f},{c:.1f}" for a, c in top + bot[::-1])
        out.append(f'<polygon points="{poly}" fill="{ORANGE_SOFT}"><title>Faixa lower–upper</title></polygon>')
    out.append(f'<path d="{step_path(lambda x: x["tg"].get(k))}" fill="none" stroke="{ORANGE}" stroke-width="2"/>')
    last = pts[-1]
    out.append(f'<g><title>Target atual: {e(fmt(last["tg"][k]))} ({clock.fmt(clock.ms(last["t"]))})</title>'
               f'<circle cx="{sx(last["t"]):.1f}" cy="{sy(last["tg"][k]):.1f}" r="4" fill="{ORANGE}" stroke="#fff" stroke-width="2"/></g>')
    out.append("</svg>")
    return "".join(out)


def replica_bullets(hpas, title, W=1100):
    """Réplicas atuais (barra azul) dentro de min–max (faixa cinza); traço = desired."""
    if not hpas:
        return '<p class="empty">Nenhum HPA.</p>'
    row_h, label_w = 30, 230
    x0, x1 = label_w, W - 60
    H = 12 + len(hpas) * row_h + 24
    vmax = nice_max(max([(h.get("maxReplicas") or 1) for h in hpas] + [1]))
    sx = lambda v: x0 + (x1 - x0) * (v or 0) / vmax
    out = [svg_open(W, H, title), x_axis(x0, x1, 6, H - 24, vmax, lambda v: nf(v))]
    y = 10
    for h in hpas:
        cy = y + row_h / 2
        name = f'{h["namespace"]}/{h["name"]}'
        mn, mx, cur, des = h.get("minReplicas") or 0, h.get("maxReplicas") or 0, h.get("currentReplicas") or 0, h.get("desiredReplicas")
        out.append(lab_text(x0 - 10, cy + 4, name, 34))
        out.append(f'<g><title>minReplicas {mn} – maxReplicas {mx}</title><rect x="{sx(mn):.1f}" y="{cy - 9:.1f}" '
                   f'width="{max(1, sx(mx) - sx(mn)):.1f}" height="18" rx="3" fill="#ecebe8"/></g>')
        out.append(f'<g><title>{e(name)} · current {cur} · desired {des}</title><rect x="{x0}" y="{cy - 5:.1f}" '
                   f'width="{max(0.5, sx(cur) - x0):.1f}" height="10" rx="2" fill="{BLUE}"/></g>')
        if des is not None and des != cur:
            out.append(f'<line x1="{sx(des):.1f}" y1="{cy - 10:.1f}" x2="{sx(des):.1f}" y2="{cy + 10:.1f}" stroke="{INK}" stroke-width="2"/>')
        out.append(f'<text x="{x1 + 8}" y="{cy + 4:.1f}" class="val">{cur} / {mx}</text>')
        y += row_h
    out.append("</svg>")
    return legend([(BLUE, "Current replicas"), ("#ecebe8", "minReplicas – maxReplicas"), (INK, "Desired (quando diferente)")]) + "".join(out)


# ---------------------------------------------------------------- tabelas

def table(head, rows, num_cols=(), cls=""):
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{e(h)}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    if not rows:
        body = f'<tr><td colspan="{len(head)}" class="empty">Sem dados.</td></tr>'
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def kpi(label, value, hint="", status=None):
    return (f'<div class="kpi"><div class="kl">{e(label)}</div><div class="kv">{value}</div>'
            f'<div class="kh">{pill(*status) if status else ""}{(" " if status and hint else "")}{e(hint)}</div></div>')


# ---------------------------------------------------------------- relatório

def build(d):
    clock = Clock(d.get("tz", 0))
    now = datetime.now(timezone.utc)
    gen = now.astimezone(clock.tz)
    ov, hpas, nodes, pods = d["overview"], d["hpas"], d["nodes"], d["pods"]

    # ---------- VPA
    vpa_rows, comp, over, under, cpu_req, cpu_tg, mem_req, mem_tg = [], 0, 0, 0, 0, 0, 0, 0
    by_ns = {}
    for r in ov:
        rec = r.get("rec") or {}
        tg = rec.get("target") or {}
        p = r.get("pods") or 0
        cs, ck = res_status(r.get("cpuReq"), rec, "cpu_m")
        ms, mk = res_status(r.get("memReq"), rec, "mem_mib")
        if tg:
            if ck == "ok" and mk == "ok":
                comp += 1
            if "bad" in (ck, mk):
                over += 1
            if "warn" in (ck, mk) and ("Under" in cs or "Under" in ms):
                under += 1
            cpu_req += (r.get("cpuReq") or 0) * p; cpu_tg += tg.get("cpu_m", 0) * p
            mem_req += (r.get("memReq") or 0) * p; mem_tg += tg.get("mem_mib", 0) * p
            n = by_ns.setdefault(r["namespace"], [0, 0, 0, 0])
            n[0] += (r.get("cpuReq") or 0) * p; n[1] += tg.get("cpu_m", 0) * p
            n[2] += (r.get("memReq") or 0) * p; n[3] += tg.get("mem_mib", 0) * p
        vpa_rows.append((r, rec, tg, p, (cs, ck), (ms, mk)))
    with_rec = sum(1 for x in vpa_rows if x[2])

    # ---------- HPA
    hpa_states = [(h, hpa_state(h, now)) for h in hpas]
    at_max = sum(1 for _, s in hpa_states if any(t == "At maxReplicas" for t, _ in s))
    metric_bad = sum(1 for _, s in hpa_states if any(t == "Metrics unavailable" for t, _ in s))
    conflicts = sum(1 for h in hpas if (h.get("vpa") or {}).get("kind") == "conflict")

    # ---------- nodes
    a_cpu = sum(n.get("allocCpu_m") or 0 for n in nodes); r_cpu = sum(n.get("reqCpu_m") or 0 for n in nodes)
    a_mem = sum(n.get("allocMem_mib") or 0 for n in nodes); r_mem = sum(n.get("reqMem_mib") or 0 for n in nodes)
    pct = lambda a, b: None if not b else a / b * 100

    # ---------- pods
    pod_rows, ooms, restarts = [], 0, 0
    for ns, dep, p in pods:
        for c in p["containers"]:
            lt = c.get("lastTermination")
            if lt and lt.get("reason") == "OOMKilled":
                ooms += 1
            restarts += c.get("restarts") or 0
            pod_rows.append((ns, dep, p, c))

    # ---------- montagem
    cdelta, mdelta = cpu_req - cpu_tg, mem_req - mem_tg
    hint = lambda dlt, f: "requests iguais ao target" if abs(dlt) < 1 else (f"{f(dlt)} over-provisioned" if dlt > 0 else f"{f(-dlt)} under-provisioned")
    summary = "".join([
        kpi("Deployments/containers com VPA", nf(len(vpa_rows)), f"{with_rec} com recomendação"),
        kpi("Compliant com o VPA", f"{nf(comp)}<small> / {nf(with_rec)}</small>", "requests entre lower e upper bound",
            ("Compliant", "ok") if with_rec and comp == with_rec else ("Review required", "warn") if with_rec else None),
        kpi("CPU requests → VPA target", f"{f_cpu(cpu_req)} → {f_cpu(cpu_tg)}", hint(cdelta, f_cpu)),
        kpi("Memory requests → VPA target", f"{f_mem(mem_req)} → {f_mem(mem_tg)}", hint(mdelta, f_mem)),
        kpi("HPAs", nf(len(hpas)), f"{at_max} em maxReplicas · {metric_bad} sem métricas",
            ("Review required", "warn") if at_max or metric_bad else ("Stable", "ok") if hpas else None),
        kpi("VPA × HPA conflicts", nf(conflicts), "", ("VPA conflict", "bad") if conflicts else ("Nenhum", "ok")),
        kpi("Cluster CPU requests", f"{nf(pct(r_cpu, a_cpu))}%", f"{f_cpu(r_cpu)} de {f_cpu(a_cpu)} allocatable"),
        kpi("Cluster memory requests", f"{nf(pct(r_mem, a_mem))}%", f"{f_mem(r_mem)} de {f_mem(a_mem)} allocatable"),
    ])

    findings = []
    if with_rec:
        findings.append(f"<b>{comp} de {with_rec}</b> containers com VPA estão em conformidade com a recomendação"
                        f"{'' if comp == with_rec else f'; {over} over-provisioned e {under} under-provisioned'}.")
        if abs(cdelta) >= 1 or abs(mdelta) >= 1:
            findings.append(f"Aplicando os targets do VPA, os requests mudariam em <b>{signed(-cdelta, f_cpu)}</b> de CPU "
                            f"e <b>{signed(-mdelta, f_mem)}</b> de memória.")
    if at_max:
        findings.append(f"<b>{at_max}</b> HPA(s) em maxReplicas: sem headroom para scale up.")
    if metric_bad:
        findings.append(f"<b>{metric_bad}</b> HPA(s) sem métricas (ScalingActive=False).")
    if conflicts:
        findings.append(f"<b>{conflicts}</b> combinação(ões) VPA × HPA em conflito na mesma métrica.")
    if ooms:
        findings.append(f"<b>{ooms}</b> container(s) com último término por <b>OOMKilled</b>.")
    if not findings:
        findings.append("Nenhum ponto de atenção encontrado.")

    # "somente pontos de atenção": os KPIs acima continuam com o escopo inteiro; listas e gráficos abaixo, só o que precisa de ação
    attention = d.get("attention")
    if attention:
        vpa_rows = [x for x in vpa_rows if x[2] and not (x[4][1] == "ok" and x[5][1] == "ok")]
        hpa_states = [(h, st) for h, st in hpa_states if any(t not in ("Stable", "At minReplicas") for t, _ in st)]
        keep_hpa = {(h["namespace"], h["name"]) for h, _ in hpa_states}
        d["events"] = {k: v for k, v in d["events"].items() if k in keep_hpa}
        pod_rows = [x for x in pod_rows if (x[3].get("restarts") or 0) > 0 or x[3].get("lastTermination")
                    or x[3].get("state") != "Running" or not x[2].get("ready")]
        keep_keys = {f'{r["namespace"]}/{r["deployment"]}/{r["container"]}' for r, *_ in vpa_rows}
        d["history"] = {k: v for k, v in d["history"].items() if k in keep_keys}

    # VPA: gráficos e tabela
    def lbl(r):
        return f'{r["namespace"]}/{r["deployment"]}' + (f' · {r["container"]}' if r["container"] != r["deployment"] else "")
    band_cpu = request_vs_band([(lbl(r), r.get("cpuReq"), (rec.get("lowerBound") or {}).get("cpu_m"), tg.get("cpu_m"),
                                 (rec.get("upperBound") or {}).get("cpu_m"), f_cpu) for r, rec, tg, *_ in vpa_rows], "CPU request × faixa do VPA")
    band_mem = request_vs_band([(lbl(r), r.get("memReq"), (rec.get("lowerBound") or {}).get("mem_mib"), tg.get("mem_mib"),
                                 (rec.get("upperBound") or {}).get("mem_mib"), f_mem) for r, rec, tg, *_ in vpa_rows], "Memory request × faixa do VPA")
    ns_cpu = paired_bars([(ns, v[0], v[1]) for ns, v in sorted(by_ns.items())], f_cpu, "CPU requests", "VPA target", title="CPU por namespace")
    ns_mem = paired_bars([(ns, v[2], v[3]) for ns, v in sorted(by_ns.items())], f_mem, "Memory requests", "VPA target", title="Memória por namespace")
    vpa_table = table(
        ["Namespace", "Deployment", "Container", "Mode", "Pods", "CPU request", "CPU target (bounds)", "CPU status",
         "Mem request", "Mem target (bounds)", "Mem status"],
        [[e(r["namespace"]), f'<b>{e(r["deployment"])}</b>', e(r["container"]), e(r.get("mode")), nf(p),
          f_cpu(r.get("cpuReq")),
          f'<b>{f_cpu(tg.get("cpu_m"))}</b><br><span class="muted">{f_cpu((rec.get("lowerBound") or {}).get("cpu_m"))} – {f_cpu((rec.get("upperBound") or {}).get("cpu_m"))}</span>',
          pill(*cst), f_mem(r.get("memReq")),
          f'<b>{f_mem(tg.get("mem_mib"))}</b><br><span class="muted">{f_mem((rec.get("lowerBound") or {}).get("mem_mib"))} – {f_mem((rec.get("upperBound") or {}).get("mem_mib"))}</span>',
          pill(*mst)]
         for r, rec, tg, p, cst, mst in vpa_rows],
        num_cols={4, 5, 6, 8, 9})

    # histórico (small multiples)
    hist_html = []
    for key, entries in sorted(d["history"].items())[:16]:
        hist_html.append(f'<div class="sm"><h4>{e(key.replace("/", " / "))}</h4><div class="sm2">'
                         f'<div><p class="cap">CPU target</p>{history_chart(entries, "cpu_m", f_cpu, clock, key + " CPU")}</div>'
                         f'<div><p class="cap">Memory target</p>{history_chart(entries, "mem_mib", f_mem, clock, key + " memory")}</div>'
                         f'</div></div>')
    more_hist = len(d["history"]) - 16

    # HPA
    hpa_table = table(
        ["Namespace", "HPA", "Scale target", "Replicas", "Min – max", "Metrics (current / target)", "Last scale", "Status", "VPA"],
        [[e(h["namespace"]), f'<b>{e(h["name"])}</b>', f'{e(h.get("targetKind"))}/{e(h.get("targetName"))}',
          f'{h.get("currentReplicas")}' + (f' → {h.get("desiredReplicas")}' if h.get("desiredReplicas") not in (None, h.get("currentReplicas")) else ""),
          f'{h.get("minReplicas")} – {h.get("maxReplicas")}',
          "<br>".join(f'{e(m.get("name"))}: <b>{e(m.get("current") or "?")}</b> / {e(m.get("target") or "?")}' for m in h.get("metrics", [])) or "–",
          ago(clock.iso(h.get("lastScaleTime")), gen), " ".join(pill(t, k) for t, k in st), pill(*vpa_rel(h.get("vpa")))]
         for h, st in hpa_states],
        num_cols={3, 4, 6})
    ev_rows = []
    for (ns, name), evs in d["events"].items():
        for ev in evs[:15]:
            ev_rows.append((clock.iso(ev.get("time")), ns, name, ev))
    ev_rows.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    ev_table = table(["Last seen", "Namespace", "HPA", "Type", "Reason", "Message", "Count"],
                     [[clock.fmt(t), e(ns), e(name), pill(ev.get("type") or "–", "warn" if ev.get("type") == "Warning" else "ok"),
                       f'<b>{e(ev.get("reason"))}</b>', f'<span class="msg">{e(ev.get("message"))}</span>', nf(ev.get("count"))]
                      for t, ns, name, ev in ev_rows[:60]], num_cols={6})

    # nodes
    node_cpu = paired_bars([(n["name"], pct(n.get("reqCpu_m") or 0, n.get("allocCpu_m")), pct(n.get("useCpu_m") or 0, n.get("allocCpu_m")))
                            for n in nodes], lambda v: f"{nf(v)}%", "CPU requested (% allocatable)", "CPU usage (% allocatable)",
                           a_color=BLUE, b_color=PURPLE, label_w=150, title="CPU por node")
    node_mem = paired_bars([(n["name"], pct(n.get("reqMem_mib") or 0, n.get("allocMem_mib")), pct(n.get("useMem_mib") or 0, n.get("allocMem_mib")))
                            for n in nodes], lambda v: f"{nf(v)}%", "Memory requested (% allocatable)", "Memory usage (% allocatable)",
                           a_color=BLUE, b_color=PURPLE, label_w=150, title="Memória por node")
    node_table = table(
        ["Node", "Roles", "Status", "Instance / zone", "CPU allocatable", "CPU requested", "CPU usage", "Mem allocatable",
         "Mem requested", "Mem usage", "Pods"],
        [[f'<b>{e(n["name"])}</b>', e(", ".join(n.get("roles") or [])),
          pill("Ready, SchedulingDisabled" if n.get("ready") and n.get("unschedulable") else "Ready" if n.get("ready") else "NotReady",
               "warn" if n.get("ready") and n.get("unschedulable") else "ok" if n.get("ready") else "bad")
          + (f'<br><span class="muted">{len(n.get("taints") or [])} taint(s)</span>' if n.get("taints") else ""),
          e(" · ".join(x for x in (n.get("instanceType"), n.get("zone")) if x) or "–"),
          f_cpu(n.get("allocCpu_m")), f'{f_cpu(n.get("reqCpu_m"))} <span class="muted">({nf(pct(n.get("reqCpu_m") or 0, n.get("allocCpu_m")))}%)</span>',
          f'{f_cpu(n.get("useCpu_m"))} <span class="muted">({nf(pct(n.get("useCpu_m") or 0, n.get("allocCpu_m")))}%)</span>',
          f_mem(n.get("allocMem_mib")), f'{f_mem(n.get("reqMem_mib"))} <span class="muted">({nf(pct(n.get("reqMem_mib") or 0, n.get("allocMem_mib")))}%)</span>',
          f'{f_mem(n.get("useMem_mib"))} <span class="muted">({nf(pct(n.get("useMem_mib") or 0, n.get("allocMem_mib")))}%)</span>',
          f'{nf(n.get("pods"))} / {nf(n.get("allocPods"))}']
         for n in nodes],
        num_cols={4, 5, 6, 7, 8, 9, 10})

    pod_rows.sort(key=lambda x: (-(x[3].get("restarts") or 0), x[0], x[2]["name"]))
    pod_table = table(
        ["Namespace", "Deployment", "Pod", "Node", "Phase", "Container", "State", "Restarts", "Last termination",
         "CPU usage", "CPU req / limit", "Mem usage", "Mem req / limit"],
        [[e(ns), e(dep), f'<span class="mono">{e(p["name"])}</span>', e(p.get("node")),
          pill(p.get("phase") + ("" if p.get("ready") else " · NotReady"), "ok" if p.get("phase") == "Running" and p.get("ready") else "warn"),
          e(c["name"]), pill(c.get("state") or "–", "ok" if c.get("state") == "Running" else "bad" if any(x in (c.get("state") or "") for x in ("CrashLoop", "Error", "OOM")) else "warn"),
          (f'<b class="t-bad">{nf(c.get("restarts"))}</b>' if c.get("restarts") else "0"),
          (pill(c["lastTermination"]["reason"], "bad" if c["lastTermination"]["reason"] == "OOMKilled" else "warn")
           + f'<br><span class="muted">exit {c["lastTermination"].get("exitCode")} · {ago(clock.iso(c["lastTermination"].get("finishedAt")), gen)}</span>')
          if c.get("lastTermination") else "–",
          f_cpu(c.get("cpuUse")), f'{f_cpu((c.get("requests") or {}).get("cpu_m"))} / {f_cpu((c.get("limits") or {}).get("cpu_m"))}',
          f_mem(c.get("memUse")), f'{f_mem((c.get("requests") or {}).get("mem_mib"))} / {f_mem((c.get("limits") or {}).get("mem_mib"))}']
         for ns, dep, p, c in pod_rows[:150]],
        num_cols={7, 9, 10, 11, 12})

    errors = d.get("errors") or {}
    err_html = ("<div class='callout bad'><b>Alguns dados não puderam ser coletados:</b><br>"
                + "<br>".join(f"{e(k)}: {e(v)}" for k, v in errors.items()) + "</div>") if errors else ""
    logo = '<img src="logo" alt="" class="logo" onerror="this.remove()">' if d.get("has_logo") else ""
    att_note = ('<p class="att-note">Filtro aplicado: <b>somente itens que precisam de atenção</b>. Os indicadores do resumo '
                'consideram todo o escopo selecionado.</p>') if attention else ""

    blocks = {
        "summary": ("Resumo executivo", f"""
  <div class="kpis">{summary}</div>
  <div class="callout"><h3>Principais pontos</h3><ul>{''.join(f'<li>{x}</li>' for x in findings)}</ul></div>"""),
        "vpa": ("VPA · Recomendações", f"""
  <p class="lead">Request atual de cada container comparado à recomendação do VPA. O ponto azul é o request como % do target;
  a faixa clara é o intervalo lower–upper bound. Fora da faixa indica <b>under</b> ou <b>over-provisioning</b>.</p>
  <div class="grid2">
    <figure><figcaption>CPU request × faixa do VPA</figcaption>{band_cpu}</figure>
    <figure><figcaption>Memory request × faixa do VPA</figcaption>{band_mem}</figure>
  </div>
  <div class="grid2">
    <figure><figcaption>CPU requests × target por namespace (request × pods)</figcaption>{ns_cpu}</figure>
    <figure><figcaption>Memory requests × target por namespace (request × pods)</figcaption>{ns_mem}</figure>
  </div>
  <h3>Detalhe por container</h3>{vpa_table}"""),
        "history": ("VPA · Histórico de recomendação", f"""
  <p class="lead">Evolução do target (linha) e da faixa lower–upper (área) registrada pelo painel a cada minuto, durante todo o
  período de retenção do histórico.</p>
  <div class="sms">{''.join(hist_html) or '<p class="empty">Sem histórico gravado para o escopo selecionado.</p>'}</div>
  {f'<p class="muted">+ {more_hist} container(s) não exibidos.</p>' if more_hist > 0 else ''}"""),
        "hpa": ("HPA · Scaling", f"""
  <figure><figcaption>Replicas atuais dentro de minReplicas – maxReplicas</figcaption>{replica_bullets([h for h, _ in hpa_states], 'Replicas por HPA')}</figure>
  <h3>HorizontalPodAutoscalers</h3>{hpa_table}
  <h3>Scaling events recentes</h3><p class="muted">O Kubernetes retém events por cerca de 1 hora.</p>{ev_table}"""),
        "nodes": ("Nodes", f"""
  <p class="lead">Capacidade de todos os nodes do cluster (não depende do filtro de namespaces e deployments).</p>
  <div class="grid2">
    <figure><figcaption>CPU: requested × usage (% do allocatable)</figcaption>{node_cpu}</figure>
    <figure><figcaption>Memory: requested × usage (% do allocatable)</figcaption>{node_mem}</figure>
  </div>
  {node_table}"""),
        "pods": ("Pods", f"""
  <p class="lead">Pods dos deployments com VPA ou HPA no escopo, ordenados por restarts. {kpi_inline(restarts, ooms)}</p>
  {pod_table}
  {f'<p class="muted">Exibindo 150 de {len(pod_rows)} containers.</p>' if len(pod_rows) > 150 else ''}"""),
    }
    order = [k for k in ("summary", "vpa", "history", "hpa", "nodes", "pods") if k in (d.get("sections") or blocks)]
    toc = "".join(f'<a href="#{k}">{blocks[k][0]}</a>' for k in order)
    body = "".join(f'<section id="{k}"><h2><span>{i:02d}</span>{blocks[k][0]}</h2>{blocks[k][1]}\n</section>\n'
                   for i, k in enumerate(order, 1))
    scope = d.get("scope") or {}

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(d['title'])} · Relatório · {gen.strftime('%d/%m/%Y %H:%M')}</title>
<link rel="icon" type="image/svg+xml" href="static/icon.svg">
<style>{CSS}</style></head>
<body>
<header class="cover">
  <div class="cover-in">
    <div class="brand">{logo}<div><p class="eyebrow">{e(d['title'])} · version {e(d['version'])}</p>
      <h1>Relatório de Autoscaling</h1>
      <p class="sub">Vertical Pod Autoscaler · Horizontal Pod Autoscaler · Capacidade do cluster</p></div></div>
    <dl class="meta">
      <div><dt>Cluster</dt><dd>{e(d['cluster'])}</dd></div>
      <div><dt>Gerado em</dt><dd>{gen.strftime('%d/%m/%Y %H:%M')} ({clock.label})</dd></div>
      <div><dt>Time range</dt><dd>{e(d['range_label'])}</dd></div>
      <div><dt>Gerado por</dt><dd>{e(d.get('user') or '–')}</dd></div>
      <div class="wide"><dt>Escopo</dt><dd>{e(scope.get('namespaces') or 'Todos os namespaces')} · {e(scope.get('deployments') or 'todos os deployments')}{' · somente pontos de atenção' if attention else ''}</dd></div>
    </dl>
  </div>
  <nav class="toc">{toc}<button onclick="window.print()" class="print">Salvar em PDF</button></nav>
</header>
<main>
{err_html}{att_note}
{body}</main>
<footer><p><b>{e(d['title'])}</b> · version {e(d['version'])} · gerado em {gen.strftime('%d/%m/%Y %H:%M')} ({clock.label}).</p>
<p>Ferramenta não oficial, sem vínculo ou suporte da Red Hat. Os valores são estimativas obtidas do monitoramento do cluster e das
recomendações do VPA; valide qualquer mudança em ambiente de teste antes de aplicá-la em produção.</p></footer>
</body></html>"""


def kpi_inline(restarts, ooms):
    return f"Total de <b>{nf(restarts)}</b> restarts" + (f" e <b>{nf(ooms)}</b> OOMKilled." if ooms else ".")


CSS = """
:root{--ink:#1f1f1e;--ink2:#4d4d4b;--muted:#6f6f6c;--line:#e4e4e1;--bg:#f6f6f4;--card:#fff;--accent:#2a78d6;
--ok:#3d7317;--ok-bg:#e7f2df;--warn:#8a5a00;--warn-bg:#fdf0d2;--bad:#a1300b;--bad-bg:#fbe4dc;--info:#1e5aa8;--info-bg:#e1ecfa;
--wait:#4d4d4b;--wait-bg:#ecebe8}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "Red Hat Text","Segoe UI",Helvetica,Arial,sans-serif}
h1,h2,h3,h4{font-family:"Red Hat Display","Segoe UI",Helvetica,Arial,sans-serif;margin:0}
.cover{background:linear-gradient(135deg,#0f1b2d 0%,#16304f 60%,#1d3f66 100%);color:#fff}
.cover-in{max-width:1200px;margin:0 auto;padding:40px 32px 28px;display:flex;justify-content:space-between;gap:32px;flex-wrap:wrap;align-items:flex-end}
.brand{display:flex;gap:18px;align-items:center}.logo{height:44px;background:#fff;border-radius:6px;padding:6px 8px}
.eyebrow{margin:0 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#a8c3e6}
.cover h1{font-size:34px;font-weight:600;letter-spacing:-.01em}.sub{margin:6px 0 0;color:#c9d6e6}
.meta{display:grid;grid-template-columns:repeat(2,minmax(160px,auto));gap:10px 28px;margin:0}
.meta .wide{grid-column:1/-1;max-width:520px}.att-note{margin:24px 0 0;padding:10px 14px;border-radius:6px;background:#fdf0d2;color:#5c3d00;font-size:13px}
.meta dt{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#a8c3e6}.meta dd{margin:2px 0 0;font-weight:500;word-break:break-all}
.toc{max-width:1200px;margin:0 auto;padding:0 32px;display:flex;gap:4px;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,.12)}
.toc a{color:#dbe6f3;text-decoration:none;padding:12px 12px;font-size:13px;border-bottom:2px solid transparent}
.toc a:hover{color:#fff;border-bottom-color:#4f9be8}
.print{margin-left:auto;align-self:center;background:#fff;color:#0f1b2d;border:0;border-radius:4px;padding:7px 14px;font-weight:600;cursor:pointer}
main{max-width:1200px;margin:0 auto;padding:8px 32px 40px}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:28px 28px 24px;margin-top:24px}
h2{font-size:22px;font-weight:600;display:flex;align-items:baseline;gap:12px;padding-bottom:14px;border-bottom:1px solid var(--line);margin-bottom:18px}
h2 span{font-size:13px;color:var(--accent);font-weight:700;letter-spacing:.06em}
h3{font-size:16px;font-weight:600;margin:24px 0 10px}h4{font-size:13px;font-weight:600;margin:0 0 6px;color:var(--ink2)}
.lead{color:var(--ink2);max-width:880px;margin:0 0 16px}.muted{color:var(--muted);font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.kpi{border:1px solid var(--line);border-radius:6px;padding:14px 16px;background:#fcfcfb}
.kl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.kv{font-family:"Red Hat Display","Segoe UI",Helvetica,Arial,sans-serif;font-size:24px;font-weight:600;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.kv small{font-size:15px;color:var(--muted);font-weight:500}.kh{font-size:12.5px;color:var(--ink2)}
.callout{margin-top:18px;border-left:4px solid var(--accent);background:#f1f6fc;border-radius:4px;padding:14px 18px}
.callout h3{margin:0 0 6px;font-size:14px}.callout ul{margin:0;padding-left:18px}.callout li{margin:3px 0}
.callout.bad{border-left-color:var(--bad);background:var(--bad-bg);margin-top:24px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:20px;margin-bottom:8px}
figure{margin:0 0 12px;border:1px solid var(--line);border-radius:6px;padding:14px 16px 8px}
figcaption{font-weight:600;font-size:13px;margin-bottom:8px}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;color:var(--ink2);margin-bottom:6px}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{width:12px;height:12px;border-radius:2px;display:inline-block}
svg.chart{display:block;overflow:visible}
svg .tick{font-size:11px;fill:#6f6f6c}svg .lab{font-size:12px;fill:#1f1f1e}svg .val{font-size:11px;fill:#4d4d4b;font-variant-numeric:tabular-nums}
svg g:hover rect,svg g:hover circle{filter:brightness(.9)}
.sms{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:16px}
.sm{border:1px solid var(--line);border-radius:6px;padding:12px 14px}.sm2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.cap{margin:0 0 2px;font-size:11.5px;color:var(--muted)}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th{background:#f3f3f1;text-align:left;font-weight:600;color:var(--ink2);padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap;position:sticky;top:0}
td{padding:8px 10px;border-bottom:1px solid #efefec;vertical-align:top;white-space:nowrap}tbody tr:nth-child(even) td{background:#fbfbfa}
tbody tr:hover td{background:#f1f6fc}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.empty,.empty{color:var(--muted);text-align:center;padding:16px}.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px}
.msg{display:block;min-width:280px;max-width:460px;white-space:normal}.t-bad{color:var(--bad)}
.pill{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:1px 9px 1px 3px;font-size:11.5px;font-weight:600;white-space:nowrap;margin:1px 2px 1px 0}
.pi{width:15px;height:15px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:9.5px;color:#fff}
.st-ok{background:var(--ok-bg);color:var(--ok)}.st-ok .pi{background:var(--ok)}
.st-warn{background:var(--warn-bg);color:var(--warn)}.st-warn .pi{background:#b77d00}
.st-bad{background:var(--bad-bg);color:var(--bad)}.st-bad .pi{background:var(--bad)}
.st-info{background:var(--info-bg);color:var(--info)}.st-info .pi{background:var(--info)}
.st-wait{background:var(--wait-bg);color:var(--wait)}.st-wait .pi{background:#8a8a86}
footer{max-width:1200px;margin:0 auto;padding:8px 32px 40px;color:var(--muted);font-size:12px}
@media (max-width:700px){.cover-in,main,.toc,footer{padding-left:16px;padding-right:16px}section{padding:20px 16px}.grid2,.sms{grid-template-columns:1fr}.sm2{grid-template-columns:1fr}}
@media print{
  @page{size:A4 landscape;margin:12mm}
  body{background:#fff;font-size:11px}.toc{display:none}.cover{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  section{border:0;padding:0;margin-top:18px;break-inside:auto}section+section{break-before:page}
  figure,.kpi,.sm,tr,.callout{break-inside:avoid}.kpis{grid-template-columns:repeat(4,1fr)}.grid2{grid-template-columns:1fr 1fr}.sms{grid-template-columns:1fr 1fr}th{position:static}.tw{overflow:visible;border:0}td,th{white-space:normal}table{font-size:9.5px}
  .pill,.legend i,svg{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""
