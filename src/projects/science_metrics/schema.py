"""Definição e criação do schema lógico usado pelo Knowledge Graph no ArcadeDB.

O schema separa vértices brutos, entidades derivadas, arestas de evidência/semântica e
documentos de reporting. Índices são criados nas chaves estáveis e nos campos mais usados
pelas consultas finais.
"""

from __future__ import annotations

from projects.science_metrics.arcadedb_client import ArcadeDBClient


VERTEX_TYPES = [
    "authors",
    "institutions",
    "works",
    "researcher_seeds",
    "researcher_entities",
    "principal_institutions",
    "coauthor_entities",
]

EDGE_TYPES = [
    "AUTHORED",
    "AFFILIATED_WITH",
    "ASSOCIATED_WITH_INSTITUTION",
    "CITES",
    "CANDIDATE_FOR",
    "SAME_AS_EVIDENCE",
    "RESOLVED_AS",
    "REPRESENTS_RESEARCHER",
    "HAS_PRIMARY_INSTITUTION",
    "DERIVED_FROM_INSTITUTION",
    "RESOLVED_AS_COAUTHOR",
    "COLLABORATES_WITH",
]

DOCUMENT_TYPES = ["report_production", "report_group_summary"]


KEY_PROPERTIES = {
    "authors": ("openalex_id", "STRING"),
    "institutions": ("openalex_id", "STRING"),
    "works": ("openalex_id", "STRING"),
    "researcher_seeds": ("seed_id", "STRING"),
    "researcher_entities": ("entity_id", "STRING"),
    "principal_institutions": ("principal_id", "STRING"),
    "coauthor_entities": ("entity_id", "STRING"),
    "report_production": ("work_id", "STRING"),
    "report_group_summary": ("summary_id", "STRING"),
}


def create_schema(db: ArcadeDBClient) -> None:
    """Cria os tipos, propriedades e índices necessários para todas as camadas do projeto."""
    for type_name in VERTEX_TYPES:
        db.command(f"CREATE VERTEX TYPE {type_name} IF NOT EXISTS")
    for type_name in EDGE_TYPES:
        db.command(f"CREATE EDGE TYPE {type_name} IF NOT EXISTS")
    for type_name in DOCUMENT_TYPES:
        db.command(f"CREATE DOCUMENT TYPE {type_name} IF NOT EXISTS")

    for type_name, (field, data_type) in KEY_PROPERTIES.items():
        db.command(f"CREATE PROPERTY {type_name}.{field} IF NOT EXISTS {data_type}")
        db.command(f"CREATE INDEX IF NOT EXISTS ON {type_name} ({field}) UNIQUE")

    db.command("CREATE PROPERTY researcher_entities.selected IF NOT EXISTS BOOLEAN")
    db.command("CREATE INDEX IF NOT EXISTS ON researcher_entities (selected) NOTUNIQUE")
    db.command("CREATE PROPERTY works.publication_year IF NOT EXISTS INTEGER")
    db.command("CREATE INDEX IF NOT EXISTS ON works (publication_year) NOTUNIQUE")
    db.command("CREATE PROPERTY coauthor_entities.primary_country IF NOT EXISTS STRING")
    db.command("CREATE INDEX IF NOT EXISTS ON coauthor_entities (primary_country) NOTUNIQUE")
