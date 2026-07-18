#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
STATE_DIR="$ROOT_DIR/.runtime/mlflow"
ARTIFACT_DIR="$STATE_DIR/artifacts"
LOG_DIR="$ROOT_DIR/.runtime/logs"
PID_FILE="$ROOT_DIR/.runtime/mlflow.pid"
HOST="${MLFLOW_HOST:-127.0.0.1}"
PORT="${MLFLOW_PORT:-5000}"

mkdir -p "$STATE_DIR" "$ARTIFACT_DIR" "$LOG_DIR"

if [[ ! -x "$VENV_DIR/bin/mlflow" ]]; then
  echo "MLflow não está instalado no .venv. Execute ./scripts/install_mlflow.sh." >&2
  exit 1
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "MLflow já está em execução com PID $(cat "$PID_FILE")."
  exit 0
fi

DB_FILE="$STATE_DIR/mlflow.db"
BACKEND_URI="sqlite:///$DB_FILE"
ARTIFACT_URI="file://$ARTIFACT_DIR"

nohup "$VENV_DIR/bin/mlflow" server \
  --host "$HOST" \
  --port "$PORT" \
  --backend-store-uri "$BACKEND_URI" \
  --artifacts-destination "$ARTIFACT_URI" \
  > "$LOG_DIR/mlflow.log" 2>&1 &
echo $! > "$PID_FILE"

echo "MLflow iniciado com PID $(cat "$PID_FILE")."
echo "UI/Tracking URI: http://$HOST:$PORT"
echo "Backend SQLite: $DB_FILE"
echo "Artefatos: $ARTIFACT_DIR"
echo "Log: $LOG_DIR/mlflow.log"
