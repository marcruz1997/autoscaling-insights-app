"""Autoscaling Insights: painel do VPA e do HPA para OpenShift.

Servidor Flask que expõe uma API JSON (/api/...) e a interface em static/.
Roda atrás do oauth-proxy, que cuida do login com a conta do cluster.

Configuração por variáveis de ambiente:
  APP_TITLE          nome exibido no topo (padrão: Autoscaling Insights)
  EXCLUDE_NS_REGEX   namespaces escondidos (padrão: ^(openshift.*|kube-.*|default)$)
  THANOS_URL         padrão https://thanos-querier.openshift-monitoring.svc:9091
  KUBE_API_URL       padrão https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT
  DATA_DIR           onde gravar o histórico do VPA (padrão /data)
  HISTORY_DAYS       dias de histórico mantidos (padrão 14)
  SAMPLE_INTERVAL    segundos entre coletas do histórico (padrão 60)
  LOGO_DIR           pasta do logo opcional (padrão /logo)
  CONSOLE_LINK       "true" cria o atalho no menu de aplicações do console (ver consolelink.py)
"""
import logging
import os
import re
import time

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

import consolelink
import hpa as hpa_mod
import report as report_mod
from history import HistoryStore, start_collector
from httpclient import HttpClient
from kube import Kube
from prometheus import Prometheus, index, pick

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autoscaling-insights")


def env(key, default):
    return os.environ.get(key) or default


# ---------- configuração ----------

APP_TITLE = env("APP_TITLE", "Autoscaling Insights")
APP_VERSION = env("APP_VERSION", "dev")
KUBE_API = env("KUBE_API_URL", "https://{}:{}".format(
    env("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc"), env("KUBERNETES_SERVICE_PORT", "443")))
THANOS = env("THANOS_URL", "https://thanos-querier.openshift-monitoring.svc:9091")
LOGO_DIR = env("LOGO_DIR", "/logo")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

http = HttpClient()
kube = Kube(http, KUBE_API, env("EXCLUDE_NS_REGEX", r"^(openshift.*|kube-.*|default)$"))
prom = Prometheus(http, THANOS)
history = HistoryStore(env("DATA_DIR", "/data"), int(env("HISTORY_DAYS", "14")))
start_collector(history, kube, max(10, int(env("SAMPLE_INTERVAL", "60"))))
consolelink.start(http, KUBE_API.rstrip("/"))
log.info("versão %s", APP_VERSION)
log.info("api=%s thanos=%s histórico=%s", KUBE_API, THANOS, history.describe())

app = Flask(__name__, static_folder=None)

# Nomes válidos no Kubernetes (também evita injeção em PromQL e na URL da API).
VALID_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")

RANGES = {  # janela, step (segundos)
    "15m": (15 * 60, 15),
    "1h": (3600, 30),
    "6h": (6 * 3600, 120),
    "24h": (24 * 3600, 300),
    "7d": (7 * 24 * 3600, 1800),
}


def target_args(need_container=True):
    ns, deploy, container = (request.args.get(k, "") for k in ("ns", "deploy", "container"))
    names = [ns, deploy] + ([container] if need_container else [])
    if not all(VALID_NAME.match(n) for n in names):
        abort(400, "parâmetros ns, deploy e container são obrigatórios e devem ser nomes válidos")
    return ns, deploy, container


def range_arg():
    key = request.args.get("range", "1h")
    if key not in RANGES:
        key = "1h"
    return key, *RANGES[key]


def window_sub(window, step):
    """Subconsulta PromQL que cobre a janela escolhida: [<janela>s:<resolução>s]."""
    return f"[{int(window)}s:{max(30, int(step))}s]"


def pod_pattern(deploy):
    """Pods de um Deployment: <deployment>-<hash do replicaset>-<sufixo>."""
    return re.escape(deploy) + r"-[a-z0-9]+-[a-z0-9]+"


def promql_re(pattern):
    """Regex Python -> string para usar entre aspas no PromQL."""
    return pattern.replace("\\", "\\\\")


def with_errors(payload, errors):
    if errors:
        payload["errors"] = errors
    return jsonify(payload)


# ---------- páginas ----------

@app.get("/")
def index_page():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/static/<path:path>")
def static_files(path):
    resp = send_from_directory(STATIC_DIR, path)
    if path.startswith("vendor/"):
        resp.cache_control.max_age = 86400
    return resp


@app.get("/healthz")
def healthz():
    return "ok"


LOGO_TYPES = (("logo.svg", "image/svg+xml"), ("logo.png", "image/png"),
              ("logo.jpg", "image/jpeg"), ("logo.jpeg", "image/jpeg"))


def find_logo():
    """Logo opcional, vindo do ConfigMap vpa-dashboard-logo montado em LOGO_DIR."""
    for name, ctype in LOGO_TYPES:
        path = os.path.join(LOGO_DIR, name)
        if os.path.isfile(path):
            return path, ctype
    return None, None


@app.get("/logo")
def logo():
    path, ctype = find_logo()
    if not path:
        abort(404)
    resp = send_file(path, mimetype=ctype, max_age=300)
    # SVG servido como imagem: impede scripts embutidos no arquivo.
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return resp


@app.get("/api/branding")
def branding():
    # Público (liberado no oauth-proxy): a tela de login usa só o nome do painel.
    return jsonify({"title": APP_TITLE, "version": APP_VERSION})


@app.get("/api/config")
def config():
    # Usuário autenticado, repassado pelo oauth-proxy no cabeçalho X-Forwarded-User.
    return jsonify({
        "title": APP_TITLE,
        "version": APP_VERSION,
        "user": request.headers.get("X-Forwarded-User", ""),
        "hasLogo": find_logo()[0] is not None,
    })


# ---------- deployments e VPAs ----------

def load_vpas(errors):
    """VPAs do cluster. Sem o operador do VPA instalado (API 404) não é erro: só não há VPAs."""
    try:
        return kube.list_vpas(), True
    except Exception as exc:  # noqa: BLE001
        if "HTTP 404" in str(exc):
            return [], False
        errors["vpa"] = str(exc)
        return [], True


def load_hpas(errors):
    try:
        return hpa_mod.list_hpas(kube)
    except Exception as exc:  # noqa: BLE001
        errors["hpa"] = str(exc)
        return []


@app.get("/api/targets")
def targets():
    errors = {}
    try:
        deps = kube.list_deployments()
    except Exception as exc:  # noqa: BLE001
        errors["deployments"], deps = str(exc), []
    vpas, vpa_installed = load_vpas(errors)
    hpas = load_hpas(errors)
    with_vpa = {(v["namespace"], v["targetName"]) for v in vpas if v["targetKind"] == "Deployment"}
    with_hpa = {(h["namespace"], h["targetName"]) for h in hpas if h["targetKind"] == "Deployment"}
    for d in deps:
        d["hasVPA"] = (d["namespace"], d["name"]) in with_vpa
        d["hasHPA"] = (d["namespace"], d["name"]) in with_hpa
    for h in hpas:
        h["vpa"] = hpa_mod.vpa_relation(h, vpas)
    return with_errors({"deployments": deps, "vpas": vpas, "hpas": hpas, "vpaInstalled": vpa_installed,
                        "historyPersistent": history.persistent}, errors)


# ---------- visão geral ----------

def _aggregate(samples, match, use_max=False):
    """Média (ou máximo) das amostras que casam e quantas foram."""
    vals = [v for m, v in samples if match(m)]
    if not vals:
        return None, 0
    return round(max(vals) if use_max else sum(vals) / len(vals), 1), len(vals)


@app.get("/api/overview")
def overview():
    rg, window, step = range_arg()
    win = window_sub(window, step)
    try:
        vpas = kube.list_vpas()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"rows": [], "error": str(exc)})
    try:
        containers_of = {(d["namespace"], d["name"]): d["containers"] for d in kube.list_deployments()}
    except Exception:  # noqa: BLE001
        containers_of = {}

    vpas = [v for v in vpas if v["targetKind"] == "Deployment"]
    if not vpas:
        return jsonify({"rows": []})
    ns_re = "|".join(promql_re(re.escape(n)) for n in sorted({v["namespace"] for v in vpas}))
    sel = f'namespace=~"{ns_re}",container!="",container!="POD"'
    by = "namespace,pod,container"
    errors = {}
    data = prom.query_many({
        "cpu": f"sum by ({by}) (rate(container_cpu_usage_seconds_total{{{sel}}}[5m])) * 1000",
        "cpuP90": f"quantile_over_time(0.9, (sum by ({by}) (rate(container_cpu_usage_seconds_total{{{sel}}}[5m]))){win}) * 1000",
        "mem": f"sum by ({by}) (container_memory_working_set_bytes{{{sel}}}) / 1048576",
        "memMax": f"max_over_time((sum by ({by}) (container_memory_working_set_bytes{{{sel}}})){win}) / 1048576",
        "cpuReq": f'max by ({by}) (kube_pod_container_resource_requests{{namespace=~"{ns_re}",resource="cpu"}}) * 1000',
        "memReq": f'max by ({by}) (kube_pod_container_resource_requests{{namespace=~"{ns_re}",resource="memory"}}) / 1048576',
    }, errors)

    rows = []
    for v in vpas:
        pod_re = re.compile("^" + pod_pattern(v["targetName"]) + "$")
        recs = {c["name"]: c for c in v["containers"]}
        names = containers_of.get((v["namespace"], v["targetName"])) or sorted(recs)
        for cname in names:
            def match(m, ns=v["namespace"], c=cname):
                return m.get("namespace") == ns and m.get("container") == c and pod_re.match(m.get("pod", ""))
            cpu_use, pods = _aggregate(data["cpu"], match)
            rows.append({
                "namespace": v["namespace"], "deployment": v["targetName"], "container": cname,
                "vpa": v["name"], "mode": v["updateMode"], "pods": pods,
                "cpuUse": cpu_use,
                "cpuP90": _aggregate(data["cpuP90"], match)[0],
                "memUse": _aggregate(data["mem"], match)[0],
                "memMax": _aggregate(data["memMax"], match, use_max=True)[0],
                "cpuReq": _aggregate(data["cpuReq"], match)[0],
                "memReq": _aggregate(data["memReq"], match)[0],
                "rec": recs.get(cname),
                "conditions": v["conditions"],
            })
    rows.sort(key=lambda r: (r["namespace"], r["deployment"], r["container"]))
    return with_errors({"rows": rows, "range": rg}, errors)


# ---------- métricas detalhadas de um deployment ----------

@app.get("/api/metrics")
def metrics():
    ns, deploy, container = target_args()
    rg, window, step = range_arg()
    end = time.time()
    pods = promql_re(pod_pattern(deploy))
    sel = f'namespace="{ns}",container="{container}",pod=~"{pods}"'
    pod_sel = f'namespace="{ns}",pod=~"{pods}"'
    rate = "2m" if step < 120 else f"{2 * step}s"  # janelas longas: rate cobrindo o step inteiro
    errors = {}
    out = {"namespace": ns, "deployment": deploy, "container": container, "range": rg, "stepSeconds": step}
    out.update(prom.range_many({
        "cpu": f"sum by (pod) (rate(container_cpu_usage_seconds_total{{{sel}}}[{rate}])) * 1000",
        "memory": f"sum by (pod) (container_memory_working_set_bytes{{{sel}}}) / 1048576",
        "memRss": f"sum by (pod) (container_memory_rss{{{sel}}}) / 1048576",
        "netRx": f"sum by (pod) (rate(container_network_receive_bytes_total{{{pod_sel}}}[{rate}])) / 1024",
        "netTx": f"sum by (pod) (rate(container_network_transmit_bytes_total{{{pod_sel}}}[{rate}])) / 1024",
        "throttle": f"100 * sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{{{sel}}}[{rate}]))"
                    f" / clamp_min(sum by (pod) (rate(container_cpu_cfs_periods_total{{{sel}}}[{rate}])), 1e-9)",
        "cpuReq": f'max(kube_pod_container_resource_requests{{{sel},resource="cpu"}}) * 1000',
        "memReq": f'max(kube_pod_container_resource_requests{{{sel},resource="memory"}}) / 1048576',
        "cpuLim": f'max(kube_pod_container_resource_limits{{{sel},resource="cpu"}}) * 1000',
        "memLim": f'max(kube_pod_container_resource_limits{{{sel},resource="memory"}}) / 1048576',
        "restarts": f"sum by (pod) (kube_pod_container_status_restarts_total{{{sel}}})",
    }, "pod", end - window, end, step, errors))
    return with_errors(out, errors)


# ---------- histórico das recomendações ----------

@app.get("/api/history")
def history_api():
    ns, deploy, container = target_args()
    rg, window, _ = range_arg()
    key = f"{ns}/{deploy}/{container}"
    return jsonify({
        "range": rg,
        "entries": history.get(key, int((time.time() - window) * 1000)),
        "since": history.first(key),
        "persistent": history.persistent,
    })


# ---------- pods ----------

@app.get("/api/pods")
def pods_api():
    ns, deploy, _ = target_args(need_container=False)
    rg, window, step = range_arg()
    win = window_sub(window, step)
    errors = {}
    try:
        pods = kube.list_deployment_pods(ns, deploy)
    except Exception as exc:  # noqa: BLE001
        errors["pods"], pods = str(exc), []
    sel = f'namespace="{ns}",pod=~"{promql_re(pod_pattern(deploy))}",container!="",container!="POD"'
    cpu_q = f"sum by (pod,container) (rate(container_cpu_usage_seconds_total{{{sel}}}[5m]))"
    mem_q = f"sum by (pod,container) (container_memory_working_set_bytes{{{sel}}})"
    data = prom.query_many({
        "cpu": f"{cpu_q} * 1000",
        "mem": f"{mem_q} / 1048576",
        # na janela escolhida
        "cpuMax": f"max_over_time(({cpu_q}){win}) * 1000",
        "memMax": f"max_over_time(({mem_q}){win}) / 1048576",
        "restartsWin": f"sum by (pod,container) (increase(kube_pod_container_status_restarts_total{{{sel}}}[{int(window)}s]))",
    }, errors)
    idx = {k: index(v, "pod", "container") for k, v in data.items()}
    for p in pods:
        for c in p["containers"]:
            key = f'{p["name"]}/{c["name"]}'
            c["cpuUse"], c["memUse"] = pick(idx["cpu"], key), pick(idx["mem"], key)
            c["cpuMax"], c["memMax"] = pick(idx["cpuMax"], key), pick(idx["memMax"], key)
            rw = idx["restartsWin"].get(key)
            c["restartsWin"] = None if rw is None else int(round(rw))
    return with_errors({"pods": pods, "range": rg}, errors)


# ---------- nós ----------

@app.get("/api/nodes")
def nodes_api():
    rg, window, step = range_arg()
    win = window_sub(window, step)
    errors = {}
    try:
        nodes = kube.list_nodes()
    except Exception as exc:  # noqa: BLE001
        errors["nodes"], nodes = str(exc), []
    active = 'max by (namespace,pod) (kube_pod_status_phase{phase=~"Pending|Running"} == 1)'
    node_cpu = 'sum by (instance) (rate(node_cpu_seconds_total{mode!~"idle|iowait|steal"}[5m]))'
    node_mem = "sum by (instance) (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)"
    data = prom.query_many({
        "reqCpu": f'sum by (node) (kube_pod_container_resource_requests{{resource="cpu"}} * on (namespace,pod) group_left() {active}) * 1000',
        "reqMem": f'sum by (node) (kube_pod_container_resource_requests{{resource="memory"}} * on (namespace,pod) group_left() {active}) / 1048576',
        "useCpu": f"{node_cpu} * 1000",
        "useMem": f"{node_mem} / 1048576",
        "useCpuMax": f"max_over_time(({node_cpu}){win}) * 1000",
        "useMemMax": f"max_over_time(({node_mem}){win}) / 1048576",
        "pods": f'count by (node) (kube_pod_info{{node!=""}} * on (namespace,pod) group_left() {active})',
    }, errors)

    def by_instance(samples):
        # node-exporter usa o nome do nó em "instance"; remove uma eventual porta.
        return {m.get("instance", "").rsplit(":", 1)[0]: v for m, v in samples}

    req_cpu, req_mem, pods = index(data["reqCpu"], "node"), index(data["reqMem"], "node"), index(data["pods"], "node")
    use_cpu, use_mem = by_instance(data["useCpu"]), by_instance(data["useMem"])
    max_cpu, max_mem = by_instance(data["useCpuMax"]), by_instance(data["useMemMax"])
    for n in nodes:
        name = n["name"]
        n["reqCpu_m"], n["reqMem_mib"] = pick(req_cpu, name), pick(req_mem, name)
        n["useCpu_m"], n["useMem_mib"] = pick(use_cpu, name), pick(use_mem, name)
        n["pods"] = pick(pods, name)
        n["useCpuMax_m"], n["useMemMax_mib"] = pick(max_cpu, name), pick(max_mem, name)
    return with_errors({"nodes": nodes, "range": rg}, errors)


# ---------- armazenamento ----------

@app.get("/api/storage")
def storage_api():
    ns, deploy, _ = target_args(need_container=False)
    rg, window, step = range_arg()
    errors = {}
    try:
        pvcs = kube.list_pvcs(ns)
    except Exception as exc:  # noqa: BLE001
        errors["pvcs"], pvcs = str(exc), []
    try:
        mounted = {c for p in kube.list_deployment_pods(ns, deploy) for c in p["claims"]}
    except Exception:  # noqa: BLE001
        mounted = set()
    sel = f'namespace="{ns}"'
    data = prom.query_many({
        "used": f"max by (persistentvolumeclaim) (kubelet_volume_stats_used_bytes{{{sel}}}) / 1048576",
        "cap": f"max by (persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes{{{sel}}}) / 1048576",
        "inUsed": f"max by (persistentvolumeclaim) (kubelet_volume_stats_inodes_used{{{sel}}})",
        "inTotal": f"max by (persistentvolumeclaim) (kubelet_volume_stats_inodes{{{sel}}})",
        "growth": f"max by (persistentvolumeclaim) (delta(kubelet_volume_stats_used_bytes{{{sel}}}[{int(window)}s])) / 1048576",
    }, errors)
    idx = {k: index(v, "persistentvolumeclaim") for k, v in data.items()}
    for p in pvcs:
        n = p["name"]
        p["used_mib"], p["statsCapacity_mib"] = pick(idx["used"], n), pick(idx["cap"], n)
        p["inodesUsed"], p["inodes"] = pick(idx["inUsed"], n), pick(idx["inTotal"], n)
        p["mounted"] = n in mounted
        p["growth_mib"] = pick(idx["growth"], n)
    end = time.time()
    out = {"pvcs": pvcs, "range": rg}
    out.update(prom.range_many({
        "usedSeries": f"max by (persistentvolumeclaim) (kubelet_volume_stats_used_bytes{{{sel}}}) / 1048576",
    }, "persistentvolumeclaim", end - window, end, step, errors))
    return with_errors(out, errors)


# ---------- HPA ----------

@app.get("/api/hpa/overview")
def hpa_overview():
    rg, window, _ = range_arg()
    errors = {}
    hpas = load_hpas(errors)
    vpas, _ = load_vpas(errors)
    cur = "kube_horizontalpodautoscaler_status_current_replicas"
    by = "namespace,horizontalpodautoscaler"
    w = f"[{int(window)}s]"
    data = prom.query_many({
        "minRep": f"min by ({by}) (min_over_time({cur}{w}))",
        "maxRep": f"max by ({by}) (max_over_time({cur}{w}))",
        "changes": f"max by ({by}) (changes({cur}{w}))",
    }, errors) if hpas else {"minRep": [], "maxRep": [], "changes": []}
    idx = {k: index(v, "namespace", "horizontalpodautoscaler") for k, v in data.items()}
    for h in hpas:
        h["vpa"] = hpa_mod.vpa_relation(h, vpas)
        key = f'{h["namespace"]}/{h["name"]}'
        for field, k in (("windowMin", "minRep"), ("windowMax", "maxRep"), ("windowChanges", "changes")):
            v = idx[k].get(key)
            h[field] = None if v is None else int(round(v))
    return with_errors({"hpas": hpas, "range": rg}, errors)


@app.get("/api/hpa/detail")
def hpa_detail():
    ns, deploy, _ = target_args(need_container=False)
    rg, window, step = range_arg()
    errors = {}
    hpas = load_hpas(errors)
    in_ns = [h for h in hpas if h["namespace"] == ns]
    hpa = next((h for h in in_ns if h["targetKind"] == "Deployment" and h["targetName"] == deploy), None)
    if not hpa:
        return with_errors({"hpa": None, "others": in_ns, "range": rg}, errors)

    vpas, _ = load_vpas(errors)
    hpa["vpa"] = hpa_mod.vpa_relation(hpa, vpas)
    try:
        events = hpa_mod.list_hpa_events(kube, ns, hpa["name"])
    except Exception as exc:  # noqa: BLE001
        errors["events"], events = str(exc), []

    end = time.time()
    pods = promql_re(pod_pattern(deploy))
    use_sel = f'namespace="{ns}",pod=~"{pods}",container!="",container!="POD"'
    req_sel = f'namespace="{ns}",pod=~"{pods}"'
    hpa_sel = f'namespace="{ns}",horizontalpodautoscaler="{hpa["name"]}"'
    rate = "2m" if step < 120 else f"{2 * step}s"
    cpu_use = f"sum(rate(container_cpu_usage_seconds_total{{{use_sel}}}[{rate}]))"
    mem_use = f"sum(container_memory_working_set_bytes{{{use_sel}}})"
    pod_count = f"count(count by (pod) (container_memory_working_set_bytes{{{use_sel}}}))"
    out = {"hpa": hpa, "events": events, "range": rg, "stepSeconds": step}
    out.update(prom.range_many({
        # réplicas segundo o kube-state-metrics (o que o HPA vê e decide)
        "current": f"max(kube_horizontalpodautoscaler_status_current_replicas{{{hpa_sel}}})",
        "desired": f"max(kube_horizontalpodautoscaler_status_desired_replicas{{{hpa_sel}}})",
        "min": f"max(kube_horizontalpodautoscaler_spec_min_replicas{{{hpa_sel}}})",
        "max": f"max(kube_horizontalpodautoscaler_spec_max_replicas{{{hpa_sel}}})",
        "available": f'max(kube_deployment_status_replicas_available{{namespace="{ns}",deployment="{deploy}"}})',
        # utilização como o HPA calcula: uso total ÷ soma dos requests de todos os pods
        "cpuUtil": f'100 * {cpu_use} / sum(kube_pod_container_resource_requests{{{req_sel},resource="cpu"}})',
        "memUtil": f'100 * {mem_use} / sum(kube_pod_container_resource_requests{{{req_sel},resource="memory"}})',
        # uso médio por pod (para projetar a utilização com o request recomendado pelo VPA)
        "cpuAvg": f"1000 * {cpu_use} / {pod_count}",
        "memAvg": f"{mem_use} / 1048576 / {pod_count}",
    }, "pod", end - window, end, step, errors))
    return with_errors(out, errors)


# ---------- relatório (HTML para o navegador / PDF) ----------

RANGE_LABELS = {"15m": "últimos 15 minutos", "1h": "última 1 hora", "6h": "últimas 6 horas",
                "24h": "últimas 24 horas", "7d": "últimos 7 dias"}


REPORT_SECTIONS = ("summary", "vpa", "history", "hpa", "nodes", "pods")


def _call(view, **qs):
    """Reaproveita uma rota da API (com os mesmos parâmetros) e devolve o JSON."""
    with app.test_request_context("/", query_string=qs):
        return view().get_json()


@app.get("/report")
def report_page():
    rg, _, _ = range_arg()
    try:
        tz = max(-840, min(840, int(request.args.get("tz", "0"))))
    except ValueError:
        tz = 0
    # filtros: ns=a,b  deploy=ns/nome,ns/nome  sections=summary,vpa,...  attention=1
    ns_f = {n for n in request.args.get("ns", "").split(",") if VALID_NAME.match(n)}
    dep_f = set()
    for item in request.args.get("deploy", "").split(","):
        n, _, dname = item.partition("/")
        if VALID_NAME.match(n) and VALID_NAME.match(dname):
            dep_f.add((n, dname))
    sections = [x for x in request.args.get("sections", "").split(",") if x in REPORT_SECTIONS] or list(REPORT_SECTIONS)
    attention = request.args.get("attention") == "1"

    def keep(ns, dep=None):
        if ns_f and ns not in ns_f:
            return False
        if dep_f and dep is not None and (ns, dep) not in dep_f:
            return False
        if dep_f and dep is None and not any(n == ns for n, _ in dep_f):
            return False
        return True

    errors = {}
    ov = _call(overview, range=rg)
    if ov.get("error"):
        errors["vpa"] = ov["error"]
    ov["rows"] = [r for r in ov.get("rows", []) if keep(r["namespace"], r["deployment"])]
    ho = _call(hpa_overview, range=rg)
    errors.update({f"hpa.{k}": v for k, v in (ho.get("errors") or {}).items()})
    nd = _call(nodes_api, range=rg)
    errors.update({f"nodes.{k}": v for k, v in (nd.get("errors") or {}).items()})

    hpas = [h for h in ho.get("hpas", [])
            if keep(h["namespace"], h["targetName"] if h.get("targetKind") == "Deployment" else None)]
    events = {}
    for h in hpas:
        try:
            events[(h["namespace"], h["name"])] = hpa_mod.list_hpa_events(kube, h["namespace"], h["name"])
        except Exception as exc:  # noqa: BLE001
            errors[f'events.{h["namespace"]}/{h["name"]}'] = str(exc)

    # pods dos deployments com VPA ou HPA (limitado para não pesar em clusters grandes)
    deps = sorted({(r["namespace"], r["deployment"]) for r in ov.get("rows", [])}
                  | {(h["namespace"], h["targetName"]) for h in hpas if h.get("targetKind") == "Deployment"})
    pods = []
    for ns, dep in deps[:40]:
        if not (VALID_NAME.match(ns) and VALID_NAME.match(dep)):
            continue
        data = _call(pods_api, ns=ns, deploy=dep, range=rg)
        pods += [(ns, dep, p) for p in data.get("pods", [])]

    with history.lock:
        hist = {k: [dict(x) for x in v] for k, v in history.data.items() if keep(*k.split("/")[:2])}
    host = request.host.split(":")[0]
    cluster = host.split(".", 1)[1] if host.count(".") >= 2 and not host.replace(".", "").isdigit() else host
    html = report_mod.build({
        "title": APP_TITLE, "version": APP_VERSION, "tz": tz, "range_label": RANGE_LABELS.get(rg, rg),
        "cluster": cluster, "user": request.headers.get("X-Forwarded-User", ""),
        "overview": ov.get("rows", []), "hpas": hpas, "events": events, "nodes": nd.get("nodes", []),
        "pods": pods, "history": hist, "has_logo": find_logo()[0] is not None, "errors": errors,
        "sections": sections, "attention": attention,
        "scope": {
            "namespaces": ", ".join(sorted(ns_f)) if ns_f else "",
            "deployments": (", ".join(f"{n}/{x}" for n, x in sorted(dep_f)) if len(dep_f) <= 8
                            else f"{len(dep_f)} deployments selecionados") if dep_f else "",
        },
    })
    resp = app.response_class(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": err.description}), 400


if __name__ == "__main__":
    # Desenvolvimento local. No cluster o servidor é o gunicorn (ver Containerfile).
    app.run(host=env("HOST", "127.0.0.1"), port=int(env("PORT", "8080")))
