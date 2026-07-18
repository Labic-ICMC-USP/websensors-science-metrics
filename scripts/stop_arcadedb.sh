#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.runtime/arcadedb.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "Nenhum PID local do ArcadeDB encontrado."
  exit 0
fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "ArcadeDB encerrado (PID $PID)."
else
  echo "Processo $PID não está ativo."
fi
rm -f "$PID_FILE"
