#!/usr/bin/env python3
"""Gera o ClusterServiceVersion e os arquivos do catálogo (File-Based Catalog) do operator.

Só usa a biblioteca padrão do Python, para rodar em qualquer Mac/Linux.

  render.py csv --template T --out O --version V --replaces R --operator-image I --dashboard-image D --provider P --icon F
  render.py catalog --versions-file F --registry R --icon F --out-dir D
"""
import argparse
import base64
import datetime
import json
import os
import re
import sys

PACKAGE = "autoscaling-insights"
CHANNEL = "stable"


def b64(path):
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode()


def render_csv(a):
    with open(a.template) as fh:
        text = fh.read()
    replaces = f"  replaces: {PACKAGE}.v{a.replaces}" if a.replaces else ""
    values = {
        "__VERSION__": a.version,
        "__REPLACES__": replaces,
        "__OPERATOR_IMAGE__": a.operator_image,
        "__DASHBOARD_IMAGE__": a.dashboard_image,
        "__PROVIDER__": json.dumps(a.provider, ensure_ascii=False),  # aspas: nomes com espaço ou acento
        "__ICON_B64__": b64(a.icon),
        "__CREATED_AT__": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    for key, value in values.items():
        text = text.replace(key, value)
    # remove o comentário do topo do modelo
    text = "\n".join(l for l in text.splitlines() if not l.startswith("# ")) + "\n"
    leftover = re.findall(r"__[A-Z_]+__", text)
    if leftover:
        sys.exit(f"Erro: marcadores não preenchidos no CSV: {sorted(set(leftover))}")
    with open(a.out, "w") as fh:
        fh.write(text)


def render_catalog(a):
    with open(a.versions_file) as fh:
        versions = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    if not versions:
        sys.exit("Erro: nenhuma versão em " + a.versions_file)
    os.makedirs(a.out_dir, exist_ok=True)
    package = {
        "schema": "olm.package",
        "name": PACKAGE,
        "defaultChannel": CHANNEL,
        "description": "Painel de VPA e HPA para OpenShift. Ferramenta não oficial, sem suporte da Red Hat.",
        "icon": {"base64data": b64(a.icon), "mediatype": "image/svg+xml"},
    }
    entries = []
    for i, v in enumerate(versions):
        entry = {"name": f"{PACKAGE}.v{v}"}
        if i > 0:
            entry["replaces"] = f"{PACKAGE}.v{versions[i - 1]}"
        entries.append(entry)
    channel = {"schema": "olm.channel", "package": PACKAGE, "name": CHANNEL, "entries": entries}
    with open(os.path.join(a.out_dir, "package.json"), "w") as fh:
        json.dump(package, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(a.out_dir, "channel.json"), "w") as fh:
        json.dump(channel, fh, indent=2)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("csv")
    for flag in ("--template", "--out", "--version", "--operator-image", "--dashboard-image", "--provider", "--icon"):
        c.add_argument(flag, required=True)
    c.add_argument("--replaces", default="")
    k = sub.add_parser("catalog")
    for flag in ("--versions-file", "--icon", "--out-dir"):
        k.add_argument(flag, required=True)
    a = p.parse_args()
    render_csv(a) if a.cmd == "csv" else render_catalog(a)


if __name__ == "__main__":
    main()
