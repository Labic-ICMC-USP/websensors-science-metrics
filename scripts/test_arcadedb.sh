#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="${ARCADEDB_URL:-http://127.0.0.1:2480}"
USER="${ARCADEDB_USER:-root}"
PASSWORD="${ARCADEDB_PASSWORD:-playwithdata}"
DB="websensors_science_metrics_smoke_test"

python3 - "$URL" "$USER" "$PASSWORD" "$DB" <<'PY'
import json
import sys
import urllib.request
import urllib.error
import base64

base, user, password, db = sys.argv[1:]
base = base.rstrip("/")
auth = base64.b64encode(f"{user}:{password}".encode()).decode()
headers = {"Authorization": f"Basic {auth}", "Accept": "application/json", "Content-Type": "application/json"}

def request(path, *, payload=None, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body

try:
    status, _ = request("/api/v1/ready")
    print(f"Readiness OK: HTTP {status}")
except Exception as exc:
    raise SystemExit(f"ArcadeDB não respondeu em {base}: {exc}")

# O banco temporário isola o smoke test dos bancos reais do usuário.
for command in (f"drop database {db}",):
    try:
        request("/api/v1/server", payload={"command": command})
    except Exception:
        pass

request("/api/v1/server", payload={"command": f"create database {db}"})
status, body = request(f"/api/v1/command/{db}", payload={"language": "sql", "command": "CREATE DOCUMENT TYPE smoke_test IF NOT EXISTS"})
print(f"Comando de schema OK: HTTP {status}")
request(f"/api/v1/command/{db}", payload={"language": "sql", "command": "INSERT INTO smoke_test SET ok = true"})
status, body = request(f"/api/v1/query/{db}", payload={"language": "sql", "command": "SELECT FROM smoke_test"})
if "true" not in body.lower():
    raise SystemExit(f"Registro de teste não foi encontrado. Resposta: {body}")
print("Leitura e escrita no banco temporário concluídas com sucesso.")
request("/api/v1/server", payload={"command": f"drop database {db}"})
print("Banco temporário removido. ArcadeDB está pronto para o pipeline.")
PY
