"""Registro público dos steps disponíveis para carregamento dinâmico pelo WebSensors Flow.

Os caminhos definidos nos arquivos YAML apontam para este módulo, mantendo a configuração
do fluxo estável mesmo que a implementação interna dos steps seja reorganizada.
"""

from projects.science_metrics.ingest_data import IngestDataStep
from projects.science_metrics.model_coauthors import EnrichCoauthorsStep
from projects.science_metrics.model_identity import ResolveResearcherIdentityStep
from projects.science_metrics.model_primary_institution import InferPrincipalInstitutionStep
from projects.science_metrics.preprocess_kg import PreprocessKnowledgeGraphStep
from projects.science_metrics.reporting import BuildScienceMetricsReportsStep

__all__ = [
    "IngestDataStep",
    "PreprocessKnowledgeGraphStep",
    "ResolveResearcherIdentityStep",
    "InferPrincipalInstitutionStep",
    "EnrichCoauthorsStep",
    "BuildScienceMetricsReportsStep",
]
