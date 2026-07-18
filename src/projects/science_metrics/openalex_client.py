"""Cliente resiliente para as operações do OpenAlex usadas pela pipeline.

Além de buscas de autores e consultas por identificador, o cliente implementa paginação,
limites locais, atraso entre requisições e retentativas para respostas transitórias. Os
métodos retornam os JSONs do OpenAlex sem descartar campos, preservando a proveniência.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from projects.science_metrics.utils import short_openalex_id


class OpenAlexClient:
    """Cliente HTTP do OpenAlex com retentativas, paginação e limites configuráveis para a coleta científica."""
    def __init__(
        self,
        *,
        base_url: str = "https://api.openalex.org",
        api_key: str = "",
        mailto: str = "",
        per_page: int = 200,
        request_delay_ms: int = 120,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.mailto = mailto
        self.per_page = max(1, min(int(per_page), 200))
        self.request_delay_seconds = max(0, request_delay_ms) / 1000.0
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"Accept": "application/json", "User-Agent": "websensors-science-metrics/0.2"})

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        if self.api_key:
            query["api_key"] = self.api_key
        if self.mailto:
            query["mailto"] = self.mailto
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.get(url, params=query, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        if self.request_delay_seconds:
            time.sleep(self.request_delay_seconds)
        return data

    def search_authors(self, query: str, top_n: int = 5) -> list[dict[str, Any]]:
        """Busca os autores mais prováveis para uma consulta textual e retorna no máximo ``top_n`` candidatos."""
        params = {
            "search": query,
            "per-page": max(1, min(int(top_n), 50)),
            "select": "id,display_name,display_name_alternatives,orcid,works_count,cited_by_count,last_known_institutions,summary_stats,ids,affiliations",
        }
        try:
            data = self._get("/authors", params)
        except requests.HTTPError:
            # Keep the pipeline resilient to API-side changes in selectable fields.
            params.pop("select", None)
            data = self._get("/authors", params)
        return list(data.get("results") or [])[:top_n]

    def get_author(self, author_id: str) -> dict[str, Any]:
        """Recupera o JSON completo de um autor a partir do identificador OpenAlex."""
        return self._get(f"/authors/{short_openalex_id(author_id)}")

    def get_institution(self, institution_id: str) -> dict[str, Any]:
        """Recupera o JSON completo de uma instituição a partir do identificador OpenAlex."""
        return self._get(f"/institutions/{short_openalex_id(institution_id)}")

    def get_source(self, source_id: str) -> dict[str, Any]:
        """Recupera metadados de uma fonte de publicação a partir do identificador OpenAlex."""
        return self._get(f"/sources/{short_openalex_id(source_id)}")

    def get_work(self, work_id: str) -> dict[str, Any]:
        """Recupera o JSON completo de um trabalho científico a partir do identificador OpenAlex."""
        return self._get(f"/works/{short_openalex_id(work_id)}")

    def fetch_works_for_author(
        self,
        author_id: str,
        *,
        start_year: int | None,
        end_year: int | None,
        max_pages: int,
        on_page: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Percorre a produção de um autor com filtros opcionais de ano e limite de páginas."""
        filters = [f"authorships.author.id:{short_openalex_id(author_id)}"]
        if start_year:
            filters.append(f"from_publication_date:{int(start_year)}-01-01")
        if end_year:
            filters.append(f"to_publication_date:{int(end_year)}-12-31")
        cursor = "*"
        result: list[dict[str, Any]] = []
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self._get(
                "/works",
                {"filter": ",".join(filters), "per-page": self.per_page, "cursor": cursor},
            )
            rows = list(data.get("results") or [])
            result.extend(rows)
            if on_page:
                on_page(page, len(result))
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not rows or not cursor:
                break
        return result

    def fetch_recent_works_for_author(self, author_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Recupera uma amostra das produções mais recentes de um autor para enriquecimento de coautores."""
        params = {
            "filter": f"authorships.author.id:{short_openalex_id(author_id)}",
            "sort": "publication_date:desc",
            "per-page": max(1, min(int(limit), 200)),
            "select": "id,title,doi,publication_year,publication_date,authorships,primary_topic,topics",
        }
        try:
            data = self._get("/works", params)
        except requests.HTTPError:
            params.pop("select", None)
            data = self._get("/works", params)
        return list(data.get("results") or [])[:limit]
