# Autoscaling Insights: operator para OpenShift

Transforma o painel de VPA e HPA num operator instalável pelo **OperatorHub**. Você publica as imagens
no seu Quay uma vez. Em cada cluster, basta registrar o catálogo e instalar com um clique.

> **Importante:** ferramenta não oficial, sem vínculo ou suporte da Red Hat. Veja a página "Importante" do painel.

---

## Como funciona

```
  seu Mac (build.sh + podman)                  Quay                         cada cluster
  ───────────────────────────            ─────────────────            ──────────────────────────────
  dashboard/  ── imagem do painel ─────▶  autoscaling-insights
  operator/   ── imagem do operator ───▶  ...-operator          ◀──  operator (openshift-operators)
  bundle/     ── bundle OLM ───────────▶  ...-bundle                      │ observa InsightsDashboard
  catalog/    ── catálogo ─────────────▶  ...-catalog           ◀──  CatalogSource → OperatorHub
                                                                          ▼
                                                                   painel no namespace escolhido
```

- **Operator:** baseado em Helm (Operator SDK). Para cada recurso `InsightsDashboard`, ele instala o painel
  e mantém tudo como deveria estar: se alguém apagar a rota, o deployment ou as permissões, o operator recria.
- **Configuração:** fica no `spec` do recurso (título, namespaces escondidos, logo, histórico, volume, rota).
- **Atualizações:** cada versão publicada entra no canal `stable` e chega aos clusters pelo próprio OLM.

---

## 1. Preparar (uma vez)

No Mac:

```bash
brew install podman
podman machine init && podman machine start      # se ainda não tiver uma máquina do podman
podman login quay.io
```

No Quay, crie (ou deixe o primeiro push criar) quatro repositórios na sua organização:
`autoscaling-insights`, `autoscaling-insights-operator`, `autoscaling-insights-bundle` e `autoscaling-insights-catalog`.

**Deixe os quatro repositórios públicos.** As imagens não têm segredos, e assim os clusters e a ferramenta de
catálogo baixam sem credencial. Se precisarem ser privados, veja "Repositórios privados" no fim.

Edite o `config.env`:

```bash
REGISTRY=quay.io/marcruz
VERSION=1.0.0
PROVIDER="KubeTech Lab"
```

## 2. Publicar

```bash
./build.sh
```

O script constrói e publica as quatro imagens e gera o `deploy/catalogsource.yaml`. No Mac com chip
Apple, ele constrói para `linux/amd64` por emulação, então a primeira vez leva alguns minutos.

## 3. Instalar num cluster

```bash
oc login ...                                   # cluster-admin
oc apply -f deploy/catalogsource.yaml
```

Depois de um ou dois minutos, no console: **Operators → OperatorHub**, procure **Autoscaling Insights**
(fonte "Autoscaling Insights (não oficial)") e clique em **Install**. Use as opções padrão:
todos os namespaces, canal `stable`.

Ao terminar, o console oferece criar o **InsightsDashboard**. Aceite, ou crie pela linha de comando:

```bash
oc new-project autoscaling-insights
oc apply -n autoscaling-insights -f - <<'EOF'
apiVersion: insights.autoscaling.local/v1alpha1
kind: InsightsDashboard
metadata:
  name: autoscaling-insights
spec:
  title: Autoscaling Insights
EOF
```

A URL do painel:

```bash
oc -n autoscaling-insights get route autoscaling-insights -o jsonpath='https://{.spec.host}{"\n"}'
```

Também dá para instalar tudo pela linha de comando com `oc apply -f deploy/install-cli.yaml`.

### Logo

```bash
./set-logo.sh caminho/do/logo.png
```

### Se o painel já estiver instalado pelos scripts (versão manual)

Os dois convivem sem conflito: os nomes de namespace, rota e permissões são diferentes
(`vpa-dashboard` na manual, `autoscaling-insights` no operator). Quando o painel do operator estiver
funcionando, você pode remover o manual:

```bash
# na pasta do pacote manual (autoscaling-insights)
./remover-dashboard.sh -n vpa-dashboard -t -p
```

O histórico do VPA recomeça no painel novo, porque o volume é outro.

---

## Configuração (`spec` do InsightsDashboard)

| Campo | Padrão | Para quê |
|---|---|---|
| `title` | `Autoscaling Insights` | Nome no topo e na tela de login |
| `excludeNamespaces` | `^(openshift.*\|kube-.*\|default)$` | Namespaces escondidos (regex). `^$` mostra todos |
| `historyDays` | `14` | Dias de histórico das recomendações do VPA |
| `sampleIntervalSeconds` | `60` | Intervalo de gravação do histórico |
| `logoConfigMap` | `autoscaling-insights-logo` | ConfigMap com `logo.png`, `logo.svg` ou `logo.jpg` |
| `sessionDuration` | `8h0m0s` | Duração da sessão de login |
| `route.host` | vazio | Endereço da rota. Vazio deixa o OpenShift gerar |
| `storage.size` / `storage.storageClassName` | `1Gi` / padrão | Volume do histórico |
| `consoleLink.enabled` | `true` | Atalho no menu de aplicações do console (ícone de grade no topo), como o do Argo CD |
| `consoleLink.section` | `Autoscaling Insights` | Grupo do atalho no menu |
| `consoleLink.text` | vazio (usa `title`) | Texto do atalho |
| `oauthProxyImage` | `registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.16` | Imagem do login |

Para usar o oauth-proxy da mesma versão do seu cluster:

```bash
oc -n openshift get istag oauth-proxy:v4.4 -o jsonpath='{.image.dockerImageReference}{"\n"}'
# copie o resultado para spec.oauthProxyImage
```

---

### Atalho no console

O painel cria um item no menu de aplicações do console (ícone de grade no canto superior direito),
apontando para a própria rota. O item aparece em até um minuto depois que o pod sobe e é apagado
junto com o painel. Para desligar, use `consoleLink.enabled: false` e apague o item que já existe:
`oc delete consolelink autoscaling-insights`.

---

## Publicar uma nova versão

1. Altere o código em `dashboard/` (ou o chart em `operator/helm-charts/`).
2. Aumente `VERSION` no `config.env` (ex.: `1.0.1`).
3. Rode `./build.sh`.

Os clusters com aprovação automática atualizam sozinhos em até 30 minutos. Para conferir:
**Operators → Installed Operators**. O arquivo `catalog/versions.txt` guarda as versões publicadas.
Mantenha a pasta `catalog/` entre um build e outro, porque o catálogo novo inclui as versões anteriores.

---

## Remover

1. Apague o `InsightsDashboard`. O operator remove o painel e as permissões de cluster dele. O volume do
   histórico é mantido de propósito: `oc -n autoscaling-insights delete pvc autoscaling-insights-data`.
2. Desinstale o operator em **Operators → Installed Operators**.
3. Remova o catálogo: `oc delete -f deploy/catalogsource.yaml`.

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Operator não aparece no OperatorHub | `oc -n openshift-marketplace get pods \| grep autoscaling`. O pod do catálogo deve estar `Running`. Se estiver em `ImagePullBackOff`, o repositório do catálogo não está público |
| Instalação parada em "Installing" | `oc -n openshift-operators get csv` e `oc -n openshift-operators describe csv autoscaling-insights.v<versão>` |
| InsightsDashboard criado e nada acontece | `oc -n openshift-operators logs deploy/autoscaling-insights-operator` |
| Painel com erro de imagem | `oc -n autoscaling-insights describe pod -l app=autoscaling-insights` (repositório privado ou tag errada) |
| Build falhou só na etapa 4/4 (catálogo) | Corrija a causa e rode `./build.sh --so-catalogo`: refaz só o catálogo, sem reconstruir as outras imagens |
| "não consegui ler o bundle" na etapa 4/4 | O repositório `autoscaling-insights-bundle` não está público (ou falta `podman login quay.io`) |
| `opm validate` falha no build | Rode `./build.sh --so-catalogo`. Se persistir, envie a saída |

### Repositórios privados

1. Crie um robot account no Quay com leitura nos quatro repositórios.
2. Adicione a credencial dele ao pull secret global de cada cluster
   (`oc get secret/pull-secret -n openshift-config` → acrescente `quay.io/minha-org` → `oc set data`).
3. No Mac, o `build.sh` usa a sua credencial do `podman login` para gerar o catálogo.

---

## Estrutura

| Pasta/arquivo | Conteúdo |
|---|---|
| `config.env` | Registry, versão e fornecedor |
| `build.sh` | Constrói e publica as imagens e gera o CatalogSource |
| `dashboard/` | Código do painel (o mesmo da versão manual) |
| `operator/` | Imagem do operator: `watches.yaml` e o chart Helm do painel |
| `bundle/` | CRD, modelo do CSV (descrição, permissões, ícone) e metadados OLM |
| `catalog/` | Catálogo (File-Based Catalog) e versões publicadas |
| `deploy/` | CatalogSource e instalação pela linha de comando |
| `tools/render.py` | Gera o CSV e os arquivos do catálogo |
| `set-logo.sh` | Coloca ou troca o logo |
