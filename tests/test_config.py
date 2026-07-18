from pathlib import Path

from projects.science_metrics.ingest_data import normalize_seeds
from projects.science_metrics.utils import safe_database_name
from websensors_flow.config import load_settings


def test_default_flow_loads():
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "flows/science_metrics/flow.yaml")
    assert settings.project.name == "websensors-science-metrics"
    assert len(settings.steps) == 6


def test_normalize_seed_and_database_name():
    seeds = normalize_seeds(["João da Silva"])
    assert seeds[0]["name"] == "João da Silva"
    assert seeds[0]["seed_id"].startswith("seed_")
    assert safe_database_name("Grupo Ciência & IA") == "grupo_ciencia_ia"
