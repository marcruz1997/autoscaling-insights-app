"""HorizontalPodAutoscaler (HPA): leitura, interpretação e relação com o VPA.

Tudo aqui é somente leitura. As funções devolvem dicionários prontos para a interface.
"""
from urllib.parse import quote

from units import cpu_m, mem_mib

# Modos do VPA que alteram os pods (qualquer um diferente de "Off").
VPA_ACTIVE_MODES = {"Auto", "Auto (padrão)", "Recreate", "Initial", "InPlaceOrRecreate"}


def _fmt_quantity(resource, value):
    """Valor de um alvo/atual em texto legível: CPU em m, memória em Mi, o resto como veio."""
    if value is None:
        return None
    if resource == "cpu":
        m = cpu_m(value)
        return f"{m}m" if m is not None else str(value)
    if resource == "memory":
        mi = mem_mib(value)
        return f"{mi:g} Mi" if mi is not None else str(value)
    return str(value)


def _metric_key(m):
    """Identifica uma métrica para casar o alvo (spec) com o valor atual (status)."""
    t = m.get("type", "")
    if t == "Resource":
        return t, m["resource"]["name"], ""
    if t == "ContainerResource":
        return t, m["containerResource"]["name"], m["containerResource"].get("container", "")
    body = m.get({"Pods": "pods", "Object": "object", "External": "external"}.get(t, ""), {})
    return t, body.get("metric", {}).get("name", ""), ""


def _parse_metrics(spec_metrics, current_metrics):
    current = {}
    for m in current_metrics or []:
        try:
            current[_metric_key(m)] = m
        except (KeyError, TypeError):
            continue
    out = []
    for m in spec_metrics or []:
        try:
            key = _metric_key(m)
        except (KeyError, TypeError):
            continue
        t, name, container = key
        body = m.get({"Resource": "resource", "ContainerResource": "containerResource", "Pods": "pods",
                      "Object": "object", "External": "external"}.get(t, ""), {})
        target = body.get("target", {})
        cur_body = current.get(key, {}).get({"Resource": "resource", "ContainerResource": "containerResource",
                                             "Pods": "pods", "Object": "object", "External": "external"}.get(t, ""), {})
        cur = cur_body.get("current", {})
        resource = name if t in ("Resource", "ContainerResource") else None
        entry = {
            "type": t,
            "name": name,
            "container": container,
            "targetType": target.get("type", ""),
            "targetUtil": target.get("averageUtilization"),
            "currentUtil": cur.get("averageUtilization"),
            "target": None,
            "current": None,
        }
        if entry["targetType"] == "Utilization":
            entry["target"] = f'{target.get("averageUtilization")}%'
            entry["current"] = f'{cur["averageUtilization"]}%' if cur.get("averageUtilization") is not None else None
        else:
            tv = target.get("averageValue", target.get("value"))
            cv = cur.get("averageValue", cur.get("value"))
            entry["target"] = _fmt_quantity(resource, tv)
            entry["current"] = _fmt_quantity(resource, cv)
        out.append(entry)
    return out


def _behavior_summary(behavior):
    """Resumo legível do spec.behavior (com os padrões do Kubernetes quando ausente)."""
    def side(b, default_window):
        b = b or {}
        window = b.get("stabilizationWindowSeconds", default_window)
        policies = []
        for p in b.get("policies", []) or []:
            unit = "%" if p.get("type") == "Percent" else " pod(s)"
            policies.append(f'até {p.get("value")}{unit} a cada {p.get("periodSeconds")}s')
        return {"window": window, "select": b.get("selectPolicy", "Max"), "policies": policies}
    behavior = behavior or {}
    return {
        "scaleUp": side(behavior.get("scaleUp"), 0),
        "scaleDown": side(behavior.get("scaleDown"), 300),
        "custom": bool(behavior),
    }


def parse_hpa(item):
    meta, spec, status = item["metadata"], item.get("spec", {}), item.get("status", {})
    ref = spec.get("scaleTargetRef", {})
    conditions = [{
        "type": c.get("type", ""), "status": c.get("status", ""), "reason": c.get("reason", ""),
        "message": c.get("message", ""), "since": c.get("lastTransitionTime", ""),
    } for c in status.get("conditions", [])]
    return {
        "namespace": meta["namespace"],
        "name": meta["name"],
        "created": meta.get("creationTimestamp", ""),
        "targetKind": ref.get("kind", ""),
        "targetName": ref.get("name", ""),
        "minReplicas": spec.get("minReplicas", 1),
        "maxReplicas": spec.get("maxReplicas", 0),
        "currentReplicas": status.get("currentReplicas", 0),
        "desiredReplicas": status.get("desiredReplicas", 0),
        "lastScaleTime": status.get("lastScaleTime", ""),
        "metrics": _parse_metrics(spec.get("metrics"), status.get("currentMetrics")),
        "behavior": _behavior_summary(spec.get("behavior")),
        "conditions": conditions,
    }


def list_hpas(kube):
    data = kube.http.get_json(f"{kube.api}/apis/autoscaling/v2/horizontalpodautoscalers")
    out = [parse_hpa(i) for i in data.get("items", []) if not kube.exclude.match(i["metadata"]["namespace"])]
    out.sort(key=lambda h: (h["namespace"], h["name"]))
    return out


def list_hpa_events(kube, ns, name):
    """Eventos do HPA (o Kubernetes guarda cerca de 1 hora por padrão)."""
    selector = f"involvedObject.kind=HorizontalPodAutoscaler,involvedObject.name={name}"
    data = kube.http.get_json(f"{kube.api}/api/v1/namespaces/{quote(ns)}/events",
                              params={"fieldSelector": selector})
    out = []
    for e in data.get("items", []):
        out.append({
            "time": e.get("lastTimestamp") or e.get("eventTime") or e.get("metadata", {}).get("creationTimestamp", ""),
            "type": e.get("type", ""),
            "reason": e.get("reason", ""),
            "message": e.get("message", ""),
            "count": e.get("count", 1),
        })
    out.sort(key=lambda e: e["time"], reverse=True)
    return out


def scaled_resources(hpa):
    """Recursos (cpu/memory) que o HPA usa como métrica de escala."""
    return {m["name"] for m in hpa["metrics"] if m["type"] in ("Resource", "ContainerResource")}


def vpa_controlled(vpa):
    """Recursos que o VPA altera de fato nos pods (vazio se o modo for Off)."""
    if vpa["updateMode"] not in VPA_ACTIVE_MODES:
        return set()
    controlled = {"cpu", "memory"}
    for p in vpa.get("policies", []):
        if p.get("mode") == "Off":
            continue
        if p.get("controlled"):
            controlled = set(p["controlled"])
    return controlled


def vpa_relation(hpa, vpas):
    """Como o HPA convive com o VPA do mesmo deployment.

    conflict: os dois mexem no mesmo recurso (o HPA mede % do request que o VPA altera).
    recommend: VPA em modo Off, só recomenda; sem conflito.
    ok: VPA ativo, mas o HPA escala por outra métrica (combinação suportada).
    none: sem VPA.
    """
    vpa = next((v for v in vpas if v["namespace"] == hpa["namespace"] and v["targetKind"] == hpa["targetKind"]
                and v["targetName"] == hpa["targetName"]), None)
    if not vpa:
        return {"kind": "none"}
    overlap = sorted(scaled_resources(hpa) & vpa_controlled(vpa))
    if overlap:
        return {"kind": "conflict", "vpa": vpa["name"], "mode": vpa["updateMode"], "resources": overlap}
    if vpa["updateMode"] not in VPA_ACTIVE_MODES:
        return {"kind": "recommend", "vpa": vpa["name"], "mode": vpa["updateMode"]}
    return {"kind": "ok", "vpa": vpa["name"], "mode": vpa["updateMode"]}
