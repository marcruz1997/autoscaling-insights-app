#!/usr/bin/env bash
# Constrói e publica no Quay as 4 imagens do Autoscaling Insights como operator:
#   1. painel     <REGISTRY>/autoscaling-insights:<VERSION>
#   2. operator   <REGISTRY>/autoscaling-insights-operator:<VERSION>
#   3. bundle     <REGISTRY>/autoscaling-insights-bundle:v<VERSION>
#   4. catálogo   <REGISTRY>/autoscaling-insights-catalog:latest (e :v<VERSION>)
# e gera deploy/catalogsource.yaml para registrar o catálogo nos clusters.
#
# Pré-requisitos: podman (logado no Quay: podman login quay.io) e python3.
# Uso:  ./build.sh            # tudo
#       ./build.sh --no-push  # só constrói, sem publicar (teste local)
#       ./build.sh --so-catalogo  # refaz só o catálogo (painel, operator e bundle já publicados)
#       ./build.sh --force        # republica uma versão que já existe (os clusters NÃO recebem a mudança)
set -euo pipefail
cd "$(dirname "$0")"
source ./config.env

PUSH=1
ONLY_CATALOG=0
FORCE=0
for arg in "$@"; do
  case $arg in
    --no-push) PUSH=0 ;;
    --so-catalogo|--só-catalogo) ONLY_CATALOG=1 ;;
    --force) FORCE=1 ;;
    *) echo "Opção desconhecida: $arg" >&2; sed -n '10,13p' "$0" >&2; exit 1 ;;
  esac
done

DASHBOARD_IMG="$REGISTRY/autoscaling-insights:$VERSION"
OPERATOR_IMG="$REGISTRY/autoscaling-insights-operator:$VERSION"
BUNDLE_IMG="$REGISTRY/autoscaling-insights-bundle:v$VERSION"
CATALOG_IMG="$REGISTRY/autoscaling-insights-catalog"

step() { echo; echo "==> $*"; }
fail() { echo "Erro: $*" >&2; exit 1; }

command -v podman >/dev/null || fail "podman não encontrado (brew install podman)."
command -v python3 >/dev/null || fail "python3 não encontrado."
[[ $REGISTRY == *SEU_ORG* ]] && fail "edite REGISTRY em config.env (ex.: quay.io/minha-org)."
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "VERSION deve ser no formato 1.2.3."
if (( PUSH )); then
  podman login --get-login "${REGISTRY%%/*}" >/dev/null 2>&1 || fail "faça login: podman login ${REGISTRY%%/*}"
fi

# Confere se a pasta está completa (ex.: depois de descompactar uma atualização pelo Finder).
for f in dashboard/Dockerfile dashboard/login/sign_in.html operator/Dockerfile operator/watches.yaml \
         operator/helm-charts/autoscaling-insights/Chart.yaml operator/helm-charts/autoscaling-insights/values.yaml \
         operator/helm-charts/autoscaling-insights/templates/deployment.yaml bundle/csv.template.yaml \
         bundle/bundle.Dockerfile bundle/metadata/annotations.yaml catalog/catalog.Dockerfile catalog/versions.txt \
         deploy/catalogsource.template.yaml tools/render.py; do
  [[ -f $f ]] || fail "arquivo faltando: $f. Restaure a pasta com o zip completo (veja o README)."
done

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

# Publica a imagem e devolve em PINNED a referência por digest (repo@sha256:...).
# O operator e o CSV usam o digest, não a tag: assim nenhum node reaproveita uma imagem
# antiga que esteja em cache com a mesma tag.
PINNED=""
build_push() {  # build_push <imagem> <contexto> [Dockerfile] [args extras]
  local img=$1 ctx=$2 file=${3:-Dockerfile}; shift 3 || true
  podman build --platform "$PLATFORM" -f "$ctx/$file" -t "$img" "$@" "$ctx"
  PINNED=$img
  if (( PUSH )); then
    rm -f "$BUILD/digest"
    podman push --digestfile "$BUILD/digest" "$img"
    if [[ -s $BUILD/digest ]]; then PINNED="${img%:*}@$(cat "$BUILD/digest")"; fi
  fi
  echo "   referência: $PINNED"
}

# (compatível com o bash 3.2 e o sed do macOS)
versions() { grep -v '^#' catalog/versions.txt | grep -v '^[[:space:]]*$' || true; }

# Trava: um número de versão publicado não pode ser reaproveitado. O OLM não atualiza
# "1.0.2 -> 1.0.2" e os nodes reutilizam a imagem antiga em cache.
if (( PUSH && ! ONLY_CATALOG && ! FORCE )) && grep -qx "$VERSION" catalog/versions.txt \
   && [[ -s catalog/autoscaling-insights/bundles/v$VERSION.json ]]; then
  fail "a versão $VERSION já foi publicada. Aumente VERSION no config.env (ex.: $(echo "$VERSION" | awk -F. '{print $1"."$2"."$3+1}')).
       Republicar o mesmo número não chega aos clusters. Para forçar mesmo assim: ./build.sh --force"
fi

if (( ONLY_CATALOG )); then
  step "--so-catalogo: pulando as etapas 1 a 3 (usa as imagens já publicadas da versão $VERSION)"
else
# ---------------------------------------------------------------- 1. painel
step "1/4 Imagem do painel: $DASHBOARD_IMG"
build_push "$DASHBOARD_IMG" dashboard Dockerfile --build-arg APP_VERSION="$VERSION"
DASHBOARD_REF=$PINNED

# ---------------------------------------------------------------- 2. operator
step "2/4 Imagem do operator: $OPERATOR_IMG"
cp -r operator "$BUILD/operator"
CHART="$BUILD/operator/helm-charts/autoscaling-insights"
mkdir -p "$CHART/files"
cp dashboard/login/sign_in.html dashboard/login/error.html "$CHART/files/"
rm -f "$CHART/files/LEIA-ME.txt"
sed -i.bak "s|__DASHBOARD_IMAGE__|$DASHBOARD_REF|" "$CHART/values.yaml"
sed -i.bak "s|^version: .*|version: $VERSION|; s|^appVersion: .*|appVersion: \"$VERSION\"|" "$CHART/Chart.yaml"
rm -f "$CHART"/*.bak
build_push "$OPERATOR_IMG" "$BUILD/operator" Dockerfile
OPERATOR_REF=$PINNED

# ---------------------------------------------------------------- 3. bundle
step "3/4 Bundle OLM: $BUNDLE_IMG"
PREV=$(versions | grep -vx "$VERSION" | tail -1 || true)
mkdir -p "$BUILD/bundle"
cp -r bundle/manifests bundle/metadata bundle/bundle.Dockerfile "$BUILD/bundle/"
python3 tools/render.py csv --template bundle/csv.template.yaml \
  --out "$BUILD/bundle/manifests/autoscaling-insights.clusterserviceversion.yaml" \
  --version "$VERSION" --replaces "$PREV" --operator-image "$OPERATOR_REF" \
  --dashboard-image "$DASHBOARD_REF" --provider "$PROVIDER" --icon bundle/icon.svg
build_push "$BUNDLE_IMG" "$BUILD/bundle" bundle.Dockerfile
fi

# ---------------------------------------------------------------- 4. catálogo
step "4/4 Catálogo: $CATALOG_IMG"
grep -qx "$VERSION" catalog/versions.txt || echo "$VERSION" >> catalog/versions.txt
PKG=catalog/autoscaling-insights
mkdir -p "$PKG/bundles"
python3 tools/render.py catalog --versions-file catalog/versions.txt --icon bundle/icon.svg --out-dir "$PKG"

# Descreve cada versão a partir da imagem do bundle publicada (feito uma vez por versão).
# O opm baixa a imagem por dentro do container: precisa de uma política de imagens
# (policy.json) e, para repositórios privados, da credencial do podman login.
echo '{"default":[{"type":"insecureAcceptAnything"}]}' > "$BUILD/policy.json"
chmod 644 "$BUILD/policy.json"
OPM_ARGS=(-v "$BUILD/policy.json:/etc/containers/policy.json:ro")
AUTH="${REGISTRY_AUTH_FILE:-$HOME/.config/containers/auth.json}"
if [[ -f $AUTH ]]; then
  cp "$AUTH" "$BUILD/auth.json"; chmod 644 "$BUILD/auth.json"
  OPM_ARGS+=(-v "$BUILD/auth.json:/auth/auth.json:ro" -e REGISTRY_AUTH_FILE=/auth/auth.json
             -v "$BUILD/auth.json:/auth/config.json:ro" -e DOCKER_CONFIG=/auth)
fi
for v in $(versions); do
  out="$PKG/bundles/v$v.json"
  [[ -s $out && $v != "$VERSION" ]] && continue
  if (( ! PUSH )); then
    echo "   (--no-push: pulando a descrição de v$v, que exige o bundle publicado)"; continue
  fi
  echo "   descrevendo bundle v$v"
  if ! podman run --rm --platform "$PLATFORM" "${OPM_ARGS[@]}" "$OPM_IMAGE" \
      render "$REGISTRY/autoscaling-insights-bundle:v$v" --output=json > "$out.tmp"; then
    rm -f "$out.tmp"
    fail "não consegui ler o bundle v$v no Quay. Confira se o repositório autoscaling-insights-bundle está público."
  fi
  mv "$out.tmp" "$out"
done

if (( PUSH )); then
  podman run --rm --platform "$PLATFORM" -v "$PWD/catalog:/catalog:ro,Z" "$OPM_IMAGE" validate /catalog/autoscaling-insights \
    || fail "o catálogo não passou na validação do opm."
  podman build --platform "$PLATFORM" -f catalog/catalog.Dockerfile --build-arg OPM_IMAGE="$OPM_IMAGE" \
    -t "$CATALOG_IMG:v$VERSION" -t "$CATALOG_IMG:latest" catalog
  podman push "$CATALOG_IMG:v$VERSION"
  podman push "$CATALOG_IMG:latest"
fi

# ---------------------------------------------------------------- CatalogSource
sed -e "s|__CATALOG_IMAGE__|$CATALOG_IMG:latest|" -e "s|__PROVIDER__|$PROVIDER|" \
  deploy/catalogsource.template.yaml > deploy/catalogsource.yaml

echo
echo "Pronto. Versão $VERSION publicada em $REGISTRY."
echo "Próximo passo, em cada cluster:  oc apply -f deploy/catalogsource.yaml"
echo "Depois: Console > Operators > OperatorHub > 'Autoscaling Insights'."
