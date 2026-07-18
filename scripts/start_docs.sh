#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
HOST="${DOCS_HOST:-127.0.0.1}"
PORT="${DOCS_PORT:-8000}"

if [[ ! -x "$VENV_DIR/bin/mkdocs" ]]; then
  echo "Dependências de documentação não instaladas." >&2
  echo "Execute: $VENV_DIR/bin/python -m pip install -e '$ROOT_DIR[docs]'" >&2
  exit 1
fi

cd "$ROOT_DIR"
exec "$VENV_DIR/bin/mkdocs" serve --dev-addr "$HOST:$PORT"
