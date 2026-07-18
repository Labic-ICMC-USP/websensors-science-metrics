#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
URL="${MLFLOW_TRACKING_URI:-http://127.0.0.1:5000}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Ambiente Python local não encontrado." >&2
  exit 1
fi

"$VENV_DIR/bin/python" - "$URL" <<'PY'
import sys
import time
import requests
import mlflow

url = sys.argv[1].rstrip("/")
last_error = None
for _ in range(20):
    try:
        response = requests.get(f"{url}/version", timeout=3)
        response.raise_for_status()
        print(f"Servidor MLflow respondeu. Versão do servidor: {response.text.strip()}")
        break
    except Exception as exc:
        last_error = exc
        time.sleep(1)
else:
    raise SystemExit(f"MLflow não respondeu em {url}: {last_error}")

mlflow.set_tracking_uri(url)
mlflow.set_experiment("websensors-science-metrics-smoke-test")
with mlflow.start_run(run_name="smoke-test"):
    mlflow.log_param("component", "mlflow")
    mlflow.log_metric("ok", 1.0)
print("Teste de escrita concluído. Abra a UI e procure o experimento websensors-science-metrics-smoke-test.")
PY
