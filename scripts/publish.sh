#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_SLUG="${REPO_SLUG:-mikelexp/Fila}"
REMOTE="${PUBLISH_REMOTE:-github}"
WORKFLOW_NAME="Release"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "Error: pasa la versión como argumento (vX.X.X o X.X.X)" >&2
    exit 1
fi

if ! [[ "$VERSION" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: versión inválida: $VERSION (esperado vX.X.X o X.X.X)" >&2
    exit 1
fi

VER="${VERSION#v}"
TAG="v${VER}"

echo "==> Release v$VER"

git diff --quiet || { echo "Error: hay cambios sin commitear en el working tree" >&2; exit 1; }
git diff --cached --quiet || { echo "Error: hay cambios sin commitear en el index" >&2; exit 1; }

if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "Error: el tag $TAG ya existe localmente" >&2
    exit 1
fi

if git ls-remote --exit-code --tags "$REMOTE" "$TAG" >/dev/null 2>&1; then
    echo "Error: el tag $TAG ya existe en $REMOTE" >&2
    exit 1
fi

BRANCH="$(git branch --show-current)"
if [ -z "$BRANCH" ]; then
    echo "Error: no hay rama activa (detached HEAD)" >&2
    exit 1
fi

NEWEST_BEFORE="$(gh run list --repo "$REPO_SLUG" --workflow "$WORKFLOW_NAME" --limit 1 --json databaseId --jq '.[0].databaseId // ""' 2>/dev/null || true)"

echo "==> Creando y subiendo el tag $TAG"
git tag -a "$TAG" -m "$TAG"
git push "$REMOTE" "$BRANCH"
git push "$REMOTE" "$TAG"

echo "==> Esperando a que arranque el workflow de release..."
RUN_ID=""
for _ in $(seq 1 60); do
    NEWEST_NOW="$(gh run list --repo "$REPO_SLUG" --workflow "$WORKFLOW_NAME" --limit 1 --json databaseId --jq '.[0].databaseId // ""' 2>/dev/null || true)"
    if [ -n "$NEWEST_NOW" ] && { [ -z "$NEWEST_BEFORE" ] || [ "$NEWEST_NOW" != "$NEWEST_BEFORE" ]; }; then
        RUN_ID="$NEWEST_NOW"
        break
    fi
    sleep 5
done

if [ -z "$RUN_ID" ]; then
    echo "Error: no apareció ningún run nuevo de '$WORKFLOW_NAME' tras $((60*5))s. Revisa https://github.com/$REPO_SLUG/actions" >&2
    exit 1
fi

echo "==> Esperando al build (run #$RUN_ID)..."
gh run watch "$RUN_ID" --repo "$REPO_SLUG" --exit-status

echo "==> Verificando el release $TAG..."
if ! gh release view "$TAG" --repo "$REPO_SLUG" --json assets --jq '.assets[].name' | grep -q "fila-${VER}-linux-x86_64.tar.gz"; then
    echo "Error: no se encontró el asset fila-$VER-linux-x86_64.tar.gz en el release $TAG" >&2
    exit 1
fi

echo "==> Actualizando AUR fila-bin..."
bash "$ROOT_DIR/scripts/aur-update.sh" "$VER"

echo "==> Release v$VER publicada en GitHub y AUR"
