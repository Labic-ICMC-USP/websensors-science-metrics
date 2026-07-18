"""Interface de linha de comando do pacote ``websensors-science-metrics``.

O comando recebe um arquivo YAML do WebSensors Flow, executa a pipeline completa e imprime
um resumo final com os pontos de acesso e consultas úteis para inspeção no ArcadeDB.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from websensors_flow.config import load_settings
from websensors_flow.runner import run_configured_flow


def build_parser() -> argparse.ArgumentParser:
    """Cria o parser de argumentos da interface de linha de comando."""
    parser = argparse.ArgumentParser(description="WebSensors Science Metrics: OpenAlex -> KG ArcadeDB -> indicadores.")
    parser.add_argument(
        "--config",
        default="flows/science_metrics/flow.yaml",
        help="Arquivo YAML do fluxo (padrão: flows/science_metrics/flow.yaml).",
    )
    return parser


def main() -> None:
    """Executa a pipeline configurada e imprime o resumo final de acesso e auditoria."""
    args = build_parser().parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Configuração não encontrada: {config_path}", file=sys.stderr)
        print("Copie flows/science_metrics/flow.example.yaml para flows/science_metrics/flow.yaml.", file=sys.stderr)
        raise SystemExit(2)
    settings = load_settings(config_path)
    result = run_configured_flow(settings)
    if result.report.status != "success":
        error_message = getattr(result.failure, "error_message", None) or "erro não especificado"
        print(f"Pipeline falhou: {error_message}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
