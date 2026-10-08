# Imagem do VPA Insights: Python 3.11 sobre Red Hat UBI 9 (pública, roda com UID arbitrário no OpenShift).
FROM registry.access.redhat.com/ubi9/python-311:latest

# Versões da interface, embutidas na imagem para o painel não depender de CDN.
ARG PATTERNFLY_VERSION=6.2.3
ARG CHARTJS_VERSION=4.4.1

USER 0
WORKDIR /opt/app-root/src

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY static/ ./static/

# Baixa o PatternFly (CSS + fontes Red Hat Text/Display) e o Chart.js do registro npm.
RUN set -eux; \
    mkdir -p static/vendor/patternfly /tmp/pf /tmp/cj; \
    curl -fsSL "https://registry.npmjs.org/@patternfly/patternfly/-/patternfly-${PATTERNFLY_VERSION}.tgz" | tar -xz -C /tmp/pf; \
    if [ -f /tmp/pf/package/patternfly.min.css ]; then cp /tmp/pf/package/patternfly.min.css static/vendor/patternfly/; \
    else cp /tmp/pf/package/patternfly.css static/vendor/patternfly/patternfly.min.css; fi; \
    if [ -f /tmp/pf/package/patternfly-addons.css ]; then cp /tmp/pf/package/patternfly-addons.css static/vendor/patternfly/; \
    else : > static/vendor/patternfly/patternfly-addons.css; fi; \
    cp -r /tmp/pf/package/assets static/vendor/patternfly/; \
    rm -rf static/vendor/patternfly/assets/images; \
    curl -fsSL "https://registry.npmjs.org/chart.js/-/chart.js-${CHARTJS_VERSION}.tgz" | tar -xz -C /tmp/cj; \
    cp /tmp/cj/package/dist/chart.umd.js static/vendor/; \
    rm -rf /tmp/pf /tmp/cj; \
    chown -R 1001:0 /opt/app-root/src; chmod -R g=u /opt/app-root/src

# Versão exibida na interface (o build.sh passa a VERSION do config.env).
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

USER 1001
EXPOSE 8080
# Um worker (o coletor do histórico roda uma vez só) com várias threads para as requisições.
# BIND=127.0.0.1:8080: só o oauth-proxy, no mesmo pod, alcança o painel.
CMD ["sh", "-c", "exec gunicorn --bind \"${BIND:-127.0.0.1:8080}\" --workers 1 --threads 8 --timeout 60 --access-logfile - --error-logfile - app:app"]
