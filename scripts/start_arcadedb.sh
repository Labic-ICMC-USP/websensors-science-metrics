#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCADE_DIR="$ROOT_DIR/.runtime/arcadedb"
DATA_DIR="$ROOT_DIR/.runtime/arcadedb-data"
LOG_DIR="$ROOT_DIR/.runtime/logs"
PID_FILE="$ROOT_DIR/.runtime/arcadedb.pid"
PASSWORD="${ARCADEDB_PASSWORD:-playwithdata}"
mkdir -p "$DATA_DIR" "$LOG_DIR"

if [[ ! -x "$ARCADE_DIR/bin/server.sh" ]]; then
  echo "ArcadeDB não instalado. Execute ./scripts/install_arcadedb.sh primeiro." >&2
  exit 1
fi
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "ArcadeDB já está em execução com PID $(cat "$PID_FILE")."
  exit 0
fi

cd "$ARCADE_DIR"
export JAVA_OPTS="${JAVA_OPTS:-} -Darcadedb.server.rootPassword=$PASSWORD -Darcadedb.server.databaseDirectory=$DATA_DIR"
nohup ./bin/server.sh > "$LOG_DIR/arcadedb.log" 2>&1 &
echo $! > "$PID_FILE"

echo "ArcadeDB iniciado com PID $(cat "$PID_FILE")."
echo "Studio/API: http://127.0.0.1:2480"
echo "Usuário: root"
echo "Senha: definida em ARCADEDB_PASSWORD (padrão local: playwithdata)"
echo "Log: $LOG_DIR/arcadedb.log"
