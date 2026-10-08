"""Atalho do painel no menu de aplicações do console do OpenShift (o ícone de grade no topo).

Cria e mantém um ConsoleLink apontando para a Route do painel, do mesmo jeito que o
OpenShift GitOps faz com o Argo CD. O endereço da Route só existe depois que o OpenShift
gera o host, por isso o próprio painel cria o atalho (o chart não tem como saber o host).

O ConsoleLink tem como "dono" o ClusterRole do painel: quando o InsightsDashboard é
apagado, o operator remove o ClusterRole e o Kubernetes apaga o atalho junto.

Variáveis de ambiente:
  CONSOLE_LINK          "true" para criar o atalho (padrão: false)
  CONSOLE_LINK_NAME     nome do ConsoleLink (padrão: autoscaling-insights)
  CONSOLE_LINK_SECTION  seção no menu (padrão: Autoscaling Insights)
  CONSOLE_LINK_TEXT     texto do item (padrão: APP_TITLE)
  CONSOLE_LINK_OWNER    ClusterRole dono do atalho (padrão: autoscaling-insights-reader)
  ROUTE_NAME            Route do painel no namespace do pod (padrão: autoscaling-insights)
"""
import logging
import os
import threading
import time

from httpclient import SA_DIR

log = logging.getLogger("autoscaling-insights.consolelink")

INTERVAL_S = 300  # confere o atalho a cada 5 minutos (recria se alguém apagar)


def _env(key, default):
    return os.environ.get(key) or default


def _namespace():
    try:
        with open(f"{SA_DIR}/namespace") as fh:
            return fh.read().strip()
    except OSError:
        return _env("POD_NAMESPACE", "")


def build_link(name, host, section, text, owner):
    """Monta o ConsoleLink. owner = ClusterRole (dict) ou None."""
    meta = {"name": name, "labels": {"app": "autoscaling-insights"}}
    if owner:
        meta["ownerReferences"] = [{
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "name": owner["metadata"]["name"],
            "uid": owner["metadata"]["uid"],
        }]
    return {
        "apiVersion": "console.openshift.io/v1",
        "kind": "ConsoleLink",
        "metadata": meta,
        "spec": {
            "href": f"https://{host}",
            "location": "ApplicationMenu",
            "text": text,
            "applicationMenu": {
                "section": section,
                "imageURL": f"https://{host}/static/icon.svg",
            },
        },
    }


def sync_once(http, api):
    """Cria ou atualiza o atalho. Devolve o href ou levanta exceção."""
    ns = _namespace()
    route_name = _env("ROUTE_NAME", "autoscaling-insights")
    name = _env("CONSOLE_LINK_NAME", "autoscaling-insights")
    route = http.get_json(f"{api}/apis/route.openshift.io/v1/namespaces/{ns}/routes/{route_name}")
    host = route.get("spec", {}).get("host") or ""
    ingress = route.get("status", {}).get("ingress") or []
    if not host and ingress:
        host = ingress[0].get("host", "")
    if not host:
        raise RuntimeError("a Route ainda não tem endereço")

    owner = None
    owner_name = _env("CONSOLE_LINK_OWNER", "autoscaling-insights-reader")
    if owner_name != "-":
        try:
            owner = http.get_json(f"{api}/apis/rbac.authorization.k8s.io/v1/clusterroles/{owner_name}")
        except Exception as exc:  # noqa: BLE001 - sem dono, o atalho só não é apagado sozinho
            log.warning("não li o ClusterRole %s (o atalho não será apagado sozinho): %s", owner_name, exc)

    link = build_link(name, host,
                      _env("CONSOLE_LINK_SECTION", "Autoscaling Insights"),
                      _env("CONSOLE_LINK_TEXT", _env("APP_TITLE", "Autoscaling Insights")),
                      owner)
    url = f"{api}/apis/console.openshift.io/v1/consolelinks"
    status, body = http.send_json("POST", url, link)
    if status == 409:  # já existe: atualiza
        status, body = http.send_json("PATCH", f"{url}/{name}", link, "application/merge-patch+json")
    if status not in (200, 201):
        msg = (body or {}).get("message", "") if isinstance(body, dict) else ""
        raise RuntimeError(f"HTTP {status} {msg}".strip())
    return link["spec"]["href"]


def start(http, api):
    """Thread que mantém o atalho. Não faz nada se CONSOLE_LINK não for true."""
    if _env("CONSOLE_LINK", "false").lower() not in ("1", "true", "yes", "sim"):
        log.info("atalho no console desativado")
        return None

    def loop():
        last = None
        while True:
            try:
                href = sync_once(http, api)
                if href != last:
                    log.info("atalho no console: %s", href)
                    last = href
                wait = INTERVAL_S
            except Exception as exc:  # noqa: BLE001 - tenta de novo; o painel segue funcionando
                log.warning("atalho no console: %s", exc)
                wait = 30 if last is None else INTERVAL_S
            time.sleep(wait)

    t = threading.Thread(target=loop, name="atalho-console", daemon=True)
    t.start()
    return t
