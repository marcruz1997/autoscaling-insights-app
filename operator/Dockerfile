# Operator do Autoscaling Insights: helm-operator do Operator SDK + o chart do painel.
# Para cada recurso InsightsDashboard, ele instala/atualiza o chart com o "spec" como valores
# e corrige qualquer objeto alterado ou apagado manualmente.
FROM quay.io/operator-framework/helm-operator:v1.42.2

ENV HOME=/opt/helm
COPY watches.yaml ${HOME}/watches.yaml
COPY helm-charts ${HOME}/helm-charts
WORKDIR ${HOME}

LABEL name="autoscaling-insights-operator" \
      summary="Operator do Autoscaling Insights (ferramenta não oficial, sem suporte da Red Hat)"
