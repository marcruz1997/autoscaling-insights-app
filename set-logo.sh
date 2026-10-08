#!/usr/bin/env bash
# Coloca (ou troca) o logo do painel instalado pelo operator.
# Uso:  ./set-logo.sh caminho/do/logo.png            (aceita .png, .svg, .jpg)
#       ./set-logo.sh -n outro-namespace logo.png
#       ./set-logo.sh --remover
# O nome do ConfigMap deve ser o mesmo do campo logoConfigMap do InsightsDashboard
# (padrão: autoscaling-insights-logo).
set -euo pipefail
NS=autoscaling-insights
CM=autoscaling-insights-logo
if [[ ${1:-} == "-n" ]]; then NS=$2; shift 2; fi
[[ $# -eq 1 ]] || { sed -n '2,7p' "$0"; exit 1; }
oc whoami >/dev/null 2>&1 || { echo "Erro: faça 'oc login' antes."; exit 1; }

if [[ $1 == "--remover" ]]; then
  oc -n "$NS" delete configmap "$CM" --ignore-not-found
else
  FILE=$1
  [[ -f $FILE ]] || { echo "Erro: arquivo não encontrado: $FILE"; exit 1; }
  EXT=$(echo "${FILE##*.}" | tr 'A-Z' 'a-z')
  case $EXT in svg|png|jpg|jpeg) ;; *) echo "Erro: use .svg, .png ou .jpg"; exit 1 ;; esac
  (( $(wc -c < "$FILE") <= 900000 )) || { echo "Erro: o arquivo passa de ~900 KB."; exit 1; }
  oc -n "$NS" create configmap "$CM" --from-file="logo.$EXT=$FILE" --dry-run=client -o yaml | oc apply -f -
fi
# Recria o pod para montar o logo novo (o operator mantém o deployment).
oc -n "$NS" delete pod -l app=autoscaling-insights --wait=false
echo ">> Pronto. Recarregue o painel em alguns segundos."
