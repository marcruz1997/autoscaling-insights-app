# Catálogo (File-Based Catalog) que faz o operator aparecer no OperatorHub.
ARG OPM_IMAGE=quay.io/operator-framework/opm:v1.72.0
FROM ${OPM_IMAGE}

ENTRYPOINT ["/bin/opm"]
CMD ["serve", "/configs", "--cache-dir=/tmp/cache"]

ADD autoscaling-insights /configs/autoscaling-insights
# Pré-gera o cache para o catálogo subir rápido no cluster.
RUN ["/bin/opm", "serve", "/configs", "--cache-dir=/tmp/cache", "--cache-only"]

LABEL operators.operatorframework.io.index.configs.v1=/configs
