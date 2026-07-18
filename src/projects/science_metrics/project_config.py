"""Funções de acesso à configuração específica do projeto Science Metrics.

Os helpers centralizam a leitura de ``pipeline.params``, a resolução de segredos por
variáveis de ambiente e a construção dos clientes de ArcadeDB e OpenAlex. Isso evita que
cada step replique regras de configuração e nomes padrão.
"""

from __future__ import annotations

from typing import Any

from projects.science_metrics.arcadedb_client import ArcadeDBClient
from projects.science_metrics.openalex_client import OpenAlexClient
from projects.science_metrics.utils import resolve_secret, safe_database_name


def params_from_context(context) -> dict[str, Any]:
    """Retorna os parâmetros específicos da pipeline armazenados no contexto do WebSensors Flow."""
    return dict(context.config.pipeline.params or {})


def group_config(context) -> dict[str, Any]:
    """Retorna a configuração do grupo e da lista de pesquisadores-semente."""
    return dict(params_from_context(context).get("group") or {})


def arcadedb_config(context) -> dict[str, Any]:
    """Retorna a configuração de conexão e ciclo de vida do ArcadeDB."""
    return dict(params_from_context(context).get("arcadedb") or {})


def openalex_config(context) -> dict[str, Any]:
    """Retorna a configuração de coleta e limites da API do OpenAlex."""
    return dict(params_from_context(context).get("openalex") or {})


def modeling_config(context) -> dict[str, Any]:
    """Retorna os parâmetros das etapas de resolução de identidade e inferência institucional."""
    return dict(params_from_context(context).get("modeling") or {})


def reporting_config(context) -> dict[str, Any]:
    """Retorna os parâmetros usados na materialização dos relatórios finais."""
    return dict(params_from_context(context).get("reporting") or {})


def database_name(context) -> str:
    """Resolve o nome seguro do banco ArcadeDB associado ao grupo analisado."""
    group = group_config(context)
    arcade = arcadedb_config(context)
    configured = arcade.get("database_name") or group.get("database_name")
    return safe_database_name(str(configured or group.get("name") or "science_metrics"))


def build_arcadedb_client(context) -> ArcadeDBClient:
    """Constrói o cliente ArcadeDB usando configuração e segredos resolvidos do contexto."""
    config = arcadedb_config(context)
    return ArcadeDBClient(
        base_url=str(config.get("base_url") or "http://127.0.0.1:2480"),
        username=str(config.get("username") or "root"),
        password=resolve_secret(config, "password", "ARCADEDB_PASSWORD", "playwithdata"),
        database=database_name(context),
        timeout_seconds=float(config.get("timeout_seconds") or 30),
    )


def build_openalex_client(context) -> OpenAlexClient:
    """Constrói o cliente OpenAlex usando configuração, chave de API e limites resolvidos do contexto."""
    config = openalex_config(context)
    return OpenAlexClient(
        base_url=str(config.get("base_url") or "https://api.openalex.org"),
        api_key=resolve_secret(config, "api_key", "OPENALEX_API_KEY", ""),
        mailto=str(config.get("mailto") or ""),
        per_page=int(config.get("per_page") or 200),
        request_delay_ms=int(config.get("request_delay_ms") or 120),
        timeout_seconds=float(config.get("timeout_seconds") or 45),
    )
