#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# Instala a pipeline, testes, documentação e observabilidade no mesmo ambiente local.
# Os extras continuam separados no pyproject para quem quiser uma instalação mínima.
python -m pip install -e ".[all]"

# O ArcadeDB também é instalado dentro de .runtime para manter o tutorial autocontido.
./scripts/install_arcadedb.sh

cat <<'EOF2'

Ambiente local preparado.

Próximos passos recomendados:
1. export ARCADEDB_PASSWORD=playwithdata
2. export OPENALEX_API_KEY=sua-chave
3. ./scripts/start_arcadedb.sh
4. ./scripts/test_arcadedb.sh
5. ./scripts/start_mlflow.sh
6. ./scripts/test_mlflow.sh
7. source .venv/bin/activate
8. websensors-science-metrics --config flows/science_metrics/flow.ppg-ccmc-tutorial.yaml

Documentação local:
  ./scripts/start_docs.sh
  http://127.0.0.1:8000

Tutorial completo:
  Tutorial-PT-BR.md
EOF2
