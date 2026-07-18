#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Ambiente Python não encontrado em $VENV_DIR." >&2
  echo "Execute ./scripts/setup_local.sh ou crie o .venv antes de instalar o MLflow." >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m pip install -e "$ROOT_DIR[observability]"
echo "MLflow instalado no ambiente local: $VENV_DIR"
"$VENV_DIR/bin/mlflow" --version
