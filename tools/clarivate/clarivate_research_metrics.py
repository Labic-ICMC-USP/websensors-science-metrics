"""
clarivate_research_metrics.py

Pipeline para combinar APIs da Clarivate:
  1) Web of Science API Expanded: localizar produções por ORCID e recuperar metadados,
     afiliações, países, organizações, citações e identificadores.
  2) Web of Science Researcher API: recuperar o perfil do pesquisador e métricas básicas.
  3) InCites Document Level Metrics API: recuperar métricas normalizadas por publicação
     em múltiplos esquemas de classificação (WoS, SDG, Citation Topics, FAPESP, CAPES etc.).

Entrada JSON aceita:
[
  {"name": "Nome do Pesquisador", "orcid": "0000-0000-0000-0000"},
  {"name": "Outro Pesquisador", "orcid": "https://orcid.org/0000-0000-0000-000X"}
]

ou:
{
  "researchers": [
    {"name": "Nome do Pesquisador", "orcid": "0000-0000-0000-0000"}
  ]
}

Dependências:
    pip install requests pandas numpy pyarrow

Exemplo:
    from clarivate_research_metrics import ClarivateResearchMetrics

    pipeline = ClarivateResearchMetrics(
        wos_api_key="SUA_CHAVE_WOS_EXPANDED",
        incites_api_key="SUA_CHAVE_INCITES",
        researcher_api_key="SUA_CHAVE_RESEARCHER_API",
        verbose=True,
    )

    outputs = pipeline.run(
        input_json="pesquisadores.json",
        start_year=2020,
        end_year=2025,
        output_dir="./output",
    )

    print(outputs)

Observações:
- O Web of Science API Expanded é usado como fonte principal das produções porque fornece
  as afiliações e os países necessários para análises mais ricas de internacionalização.
- O ORCID é usado para localizar os documentos e, a partir dos autores presentes nos
  registros, resolver o Web of Science ResearcherID mais frequente.
- O InCites aceita até 100 UTs por chamada; o código faz o batching automaticamente.
- O código preserva várias classificações do InCites como JSON dentro das colunas Parquet,
  mantendo o arquivo tabular e evitando perda de informação.
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
import requests


class ClarivateResearchMetrics:
    """
    Pipeline para coleta e agregação de métricas de pesquisadores e suas publicações.

    Saídas:
      - researchers_metrics.parquet:
          uma linha por pesquisador, com métricas agregadas do período e métricas de perfil.
      - researcher_publications_metrics.parquet:
          uma linha por pesquisador x publicação, com metadados WoS e métricas InCites.
    """

    DEFAULT_INCITES_SCHEMAS = (
        "wos",      # Web of Science Categories
        "sdg",      # UN Sustainable Development Goals
        "ct",       # Citation Topics
        "esi",      # Essential Science Indicators
        "fapesp",   # FAPESP
        "capesl1",  # CAPES Level 1
        "capesl2",  # CAPES Level 2
        "capesl3",  # CAPES Level 3
        "oecd",     # OECD
    )

    def __init__(
        self,
        wos_api_key: str,
        incites_api_key: str,
        researcher_api_key: Optional[str] = None,
        *,
        wos_base_url: str = "https://wos-api.clarivate.com/api/wos",
        researcher_base_url: str = "https://api.clarivate.com/apis/wos-researcher",
        incites_base_url: str = "https://incites-api.clarivate.com/api/incites",
        incites_schemas: Optional[Iterable[str]] = None,
        include_researcher_profile: bool = True,
        include_citation_report: bool = True,
        include_raw_profile_json: bool = True,
        include_raw_wos_json: bool = False,
        incites_esci: bool = True,
        request_timeout: int = 90,
        max_retries: int = 6,
        verbose: bool = True,
    ) -> None:
        if not wos_api_key:
            raise ValueError("wos_api_key é obrigatório.")
        if not incites_api_key:
            raise ValueError("incites_api_key é obrigatório.")

        self.wos_api_key = wos_api_key
        self.incites_api_key = incites_api_key
        self.researcher_api_key = researcher_api_key or wos_api_key

        self.wos_base_url = wos_base_url.rstrip("/")
        self.researcher_base_url = researcher_base_url.rstrip("/")
        self.incites_base_url = incites_base_url.rstrip("/")

        self.incites_schemas = tuple(
            dict.fromkeys(incites_schemas or self.DEFAULT_INCITES_SCHEMAS)
        )
        self.include_researcher_profile = include_researcher_profile
        self.include_citation_report = include_citation_report
        self.include_raw_profile_json = include_raw_profile_json
        self.include_raw_wos_json = include_raw_wos_json
        self.incites_esci = incites_esci
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.verbose = verbose

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "ClarivateResearchMetrics/1.0",
        })

        # Mantém folga em relação aos limites públicos documentados.
        self._throttle_intervals = {
            "wos": 0.40,
            "researcher": 0.23,
            "incites": 0.56,
        }
        self._last_request_at = {service: 0.0 for service in self._throttle_intervals}

    # ------------------------------------------------------------------
    # Utilitários gerais
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    @staticmethod
    def _as_list(value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            result = float(value)
            return result if math.isfinite(result) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        number = ClarivateResearchMetrics._safe_float(value)
        return int(number) if number is not None else None

    @staticmethod
    def _normalize_orcid(value: str) -> str:
        if not value:
            raise ValueError("ORCID vazio.")
        value = value.strip()
        value = re.sub(r"^https?://orcid\.org/", "", value, flags=re.I)
        value = value.upper()
        if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value):
            raise ValueError(f"ORCID inválido: {value}")
        return value

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        text = unicodedata.normalize("NFKD", str(value))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-zA-Z0-9]+", " ", text).lower().strip()
        return re.sub(r"\s+", " ", text)

    @classmethod
    def _name_similarity(cls, a: str, b: str) -> Optional[float]:
        a_norm = cls._normalize_text(a)
        b_norm = cls._normalize_text(b)
        if not a_norm or not b_norm:
            return None

        seq = SequenceMatcher(None, a_norm, b_norm).ratio()
        a_tokens = set(a_norm.split())
        b_tokens = set(b_norm.split())
        union = a_tokens | b_tokens
        jaccard = len(a_tokens & b_tokens) / len(union) if union else 0.0
        return round(max(seq, jaccard), 4)

    @classmethod
    def _flatten_objects(cls, value: Any) -> list[dict]:
        """Achata combinações comuns de dict/list sem destruir objetos folha."""
        if value is None:
            return []
        if isinstance(value, list):
            out: list[dict] = []
            for item in value:
                out.extend(cls._flatten_objects(item))
            return out
        if isinstance(value, dict):
            return [value]
        return []

    @staticmethod
    def _unique_preserve(values: Iterable[Any]) -> list:
        seen = set()
        out = []
        for value in values:
            if value is None:
                continue
            key = str(value).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    @classmethod
    def _walk_key_values(cls, obj: Any, aliases: set[str]) -> list[Any]:
        out: list[Any] = []
        aliases_lower = {a.lower() for a in aliases}

        def walk(x: Any) -> None:
            if isinstance(x, dict):
                for key, value in x.items():
                    if str(key).lower() in aliases_lower:
                        out.append(value)
                    walk(value)
            elif isinstance(x, list):
                for item in x:
                    walk(item)

        walk(obj)
        return out

    @classmethod
    def _first_scalar_by_alias(cls, obj: Any, aliases: Iterable[str]) -> Any:
        for value in cls._walk_key_values(obj, set(aliases)):
            if isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, (str, int, float, bool)):
                        return item
            if isinstance(value, dict):
                for preferred in ("value", "count", "total", "content"):
                    candidate = value.get(preferred)
                    if isinstance(candidate, (str, int, float, bool)):
                        return candidate
        return None

    @staticmethod
    def _chunked(values: list[str], size: int) -> Iterable[list[str]]:
        for i in range(0, len(values), size):
            yield values[i:i + size]

    @staticmethod
    def _clean_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza colunas problemáticas antes de gravar Parquet.
        Listas/dicts residuais são serializados em JSON para garantir esquema estável.
        """
        df = df.copy()
        for col in df.columns:
            if df[col].dtype != "object":
                continue

            non_null = df[col].dropna()
            if non_null.empty:
                continue

            if non_null.map(lambda x: isinstance(x, (dict, list, tuple, set))).any():
                df[col] = df[col].map(
                    lambda x: json.dumps(
                        list(x) if isinstance(x, set) else x,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                    if isinstance(x, (dict, list, tuple, set))
                    else x
                )
        return df

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request_json(
        self,
        service: str,
        method: str,
        url: str,
        *,
        api_key: str,
        params: Optional[dict] = None,
        allow_404: bool = False,
    ) -> Any:
        headers = {"X-ApiKey": api_key, "Accept": "application/json"}
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            now = time.monotonic()
            wait_for = self._throttle_intervals[service] - (
                now - self._last_request_at[service]
            )
            if wait_for > 0:
                time.sleep(wait_for)
            self._last_request_at[service] = time.monotonic()

            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    timeout=self.request_timeout,
                )

                if allow_404 and response.status_code == 404:
                    return None

                if response.status_code in (429, 500, 502, 503, 504):
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            sleep_for = float(retry_after)
                        except ValueError:
                            sleep_for = min(2 ** attempt, 30)
                    else:
                        sleep_for = min(2 ** attempt, 30)
                    self._log(
                        f"  HTTP {response.status_code} em {service}; "
                        f"nova tentativa em {sleep_for:.1f}s..."
                    )
                    time.sleep(sleep_for)
                    continue

                if response.status_code in (401, 403):
                    raise RuntimeError(
                        f"Falha de autenticação/autorização ({response.status_code}) em {url}. "
                        "Verifique a chave e a assinatura da API correspondente."
                    )

                response.raise_for_status()
                if not response.content:
                    return None
                return response.json()

            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt + 1 >= self.max_retries:
                    break
                sleep_for = min(2 ** attempt, 30)
                self._log(
                    f"  Erro em {service}: {exc}. "
                    f"Nova tentativa em {sleep_for:.1f}s..."
                )
                time.sleep(sleep_for)

        raise RuntimeError(
            f"Falha após {self.max_retries} tentativas em {url}: {last_error}"
        )

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def _load_input(self, input_json: str | Path | list | dict) -> list[dict]:
        if isinstance(input_json, (str, Path)):
            path = Path(input_json)
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = input_json

        if isinstance(data, dict):
            data = data.get("researchers", data.get("pesquisadores", []))

        if not isinstance(data, list):
            raise ValueError(
                "O JSON deve ser uma lista de pesquisadores ou um objeto com a chave 'researchers'."
            )

        researchers = []
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"Item {index} do JSON não é um objeto.")

            name = item.get("name") or item.get("nome")
            orcid = item.get("orcid") or item.get("ORCID")
            if not name or not orcid:
                raise ValueError(
                    f"Item {index} precisa conter 'name'/'nome' e 'orcid'."
                )

            researchers.append({
                **item,
                "name": str(name).strip(),
                "orcid": self._normalize_orcid(str(orcid)),
            })

        return researchers

    # ------------------------------------------------------------------
    # Web of Science API Expanded
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_wos_records_from_payload(payload: Any) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        records = (
            payload.get("Data", {})
            .get("Records", {})
            .get("records", {})
            .get("REC", [])
        )
        return ClarivateResearchMetrics._as_list(records)

    @staticmethod
    def _extract_query_result(payload: Any) -> dict:
        if not isinstance(payload, dict):
            return {}
        result = payload.get("QueryResult")
        return result if isinstance(result, dict) else {}

    def _wos_search_records(
        self,
        query: str,
        *,
        page_size: int = 100,
        option_view: str = "FR",
    ) -> tuple[list[dict], Optional[str], int]:
        page_size = max(1, min(int(page_size), 100))

        params = {
            "databaseId": "WOS",
            "usrQuery": query,
            "count": page_size,
            "firstRecord": 1,
            "lang": "en",
            "optionView": option_view,
        }

        payload = self._request_json(
            "wos",
            "GET",
            self.wos_base_url,
            api_key=self.wos_api_key,
            params=params,
        )

        query_result = self._extract_query_result(payload)
        query_id = query_result.get("QueryID")
        total = self._safe_int(query_result.get("RecordsFound")) or 0
        records = self._extract_wos_records_from_payload(payload)

        first_record = 1 + page_size
        while first_record <= total:
            if query_id is not None:
                url = f"{self.wos_base_url}/query/{query_id}"
                next_params = {
                    "count": page_size,
                    "firstRecord": first_record,
                    "optionView": option_view,
                }
            else:
                url = self.wos_base_url
                next_params = {
                    **params,
                    "firstRecord": first_record,
                }

            next_payload = self._request_json(
                "wos",
                "GET",
                url,
                api_key=self.wos_api_key,
                params=next_params,
            )
            next_records = self._extract_wos_records_from_payload(next_payload)
            if not next_records:
                break
            records.extend(next_records)
            first_record += page_size

        return records, str(query_id) if query_id is not None else None, total

    def _wos_query_for_orcid(
        self,
        orcid: str,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> str:
        query = f'AI=("{orcid}")'
        if start_year is not None and end_year is not None:
            query += f" AND PY=({int(start_year)}-{int(end_year)})"
        return query

    def _wos_citation_report(
        self,
        query_id: Optional[str],
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> list[dict]:
        if not query_id:
            return []

        params: dict[str, Any] = {"reportLevel": "WOS,AllDB"}
        if start_year is not None:
            params["startYear"] = str(start_year)
        if end_year is not None:
            params["endYear"] = str(end_year)

        payload = self._request_json(
            "wos",
            "GET",
            f"{self.wos_base_url}/citation-report/{query_id}",
            api_key=self.wos_api_key,
            params=params,
            allow_404=True,
        )
        return payload if isinstance(payload, list) else []

    @classmethod
    def _extract_wos_titles(cls, summary: dict) -> tuple[Optional[str], Optional[str]]:
        title_items = cls._as_list(summary.get("titles", {}).get("title"))
        item_title = None
        source_title = None
        for title in title_items:
            if not isinstance(title, dict):
                continue
            title_type = str(title.get("type", "")).lower()
            content = title.get("content")
            if title_type == "item" and content:
                item_title = content
            elif title_type == "source" and content:
                source_title = content
        return item_title, source_title

    @classmethod
    def _extract_wos_identifiers(cls, record: dict) -> dict[str, str]:
        identifiers = (
            record.get("dynamic_data", {})
            .get("cluster_related", {})
            .get("identifiers", {})
            .get("identifier", [])
        )
        out: dict[str, str] = {}
        for item in cls._as_list(identifiers):
            if not isinstance(item, dict):
                continue
            key = str(item.get("type", "")).lower().strip()
            value = item.get("value")
            if key and value:
                out[key] = str(value)
        return out

    @classmethod
    def _extract_wos_citations(cls, record: dict) -> dict[str, Optional[int]]:
        tc_list = (
            record.get("dynamic_data", {})
            .get("citation_related", {})
            .get("tc_list", {})
            .get("silo_tc", [])
        )
        out: dict[str, Optional[int]] = {}
        for item in cls._as_list(tc_list):
            if not isinstance(item, dict):
                continue
            coll = str(item.get("coll_id", "")).upper()
            if coll:
                out[coll] = cls._safe_int(item.get("local_count"))
        return out

    @classmethod
    def _extract_wos_authors(cls, summary: dict) -> list[dict]:
        names = summary.get("names", {}).get("name", [])
        return [x for x in cls._as_list(names) if isinstance(x, dict)]

    @classmethod
    def _find_matching_author(
        cls,
        authors: list[dict],
        orcid: str,
        resolved_rid: Optional[str] = None,
    ) -> Optional[dict]:
        target_orcid = cls._normalize_orcid(orcid)

        for author in authors:
            candidate = author.get("orcid_id")
            if candidate:
                try:
                    if cls._normalize_orcid(str(candidate)) == target_orcid:
                        return author
                except ValueError:
                    pass

        if resolved_rid:
            for author in authors:
                if str(author.get("r_id", "")).strip() == resolved_rid:
                    return author

        return None

    @classmethod
    def _extract_wos_addresses(cls, fullrecord: dict) -> list[dict]:
        addresses = fullrecord.get("addresses", {}).get("address_name", [])
        out = []
        for entry in cls._as_list(addresses):
            if isinstance(entry, list):
                for nested in entry:
                    if isinstance(nested, dict):
                        out.append(nested)
            elif isinstance(entry, dict):
                out.append(entry)
        return out

    @classmethod
    def _organizations_from_address(cls, address: dict) -> list[str]:
        spec = address.get("address_spec", {}) if isinstance(address, dict) else {}
        organizations = spec.get("organizations", {}).get("organization", [])
        result = []
        for org in cls._as_list(organizations):
            if isinstance(org, dict):
                content = org.get("content")
                if content:
                    result.append(str(content))
            elif isinstance(org, str):
                result.append(org)
        return cls._unique_preserve(result)

    @classmethod
    def _address_number(cls, address: dict) -> Optional[int]:
        spec = address.get("address_spec", {}) if isinstance(address, dict) else {}
        return cls._safe_int(spec.get("addr_no"))

    @classmethod
    def _author_address_numbers(cls, author: Optional[dict]) -> set[int]:
        if not author:
            return set()
        raw = author.get("addr_no", [])
        values: list[Any]
        if isinstance(raw, str):
            values = re.findall(r"\d+", raw)
        else:
            values = cls._as_list(raw)
        out = set()
        for value in values:
            parsed = cls._safe_int(value)
            if parsed is not None:
                out.add(parsed)
        return out

    @classmethod
    def _extract_wos_categories(cls, fullrecord: dict) -> list[dict]:
        subjects = (
            fullrecord.get("category_info", {})
            .get("subjects", {})
            .get("subject", [])
        )
        out = []
        for subject in cls._as_list(subjects):
            if isinstance(subject, dict):
                out.append({
                    "name": subject.get("content"),
                    "code": subject.get("code"),
                    "type": subject.get("ascatype"),
                })
            elif isinstance(subject, str):
                out.append({"name": subject, "code": None, "type": None})
        return out

    @classmethod
    def _extract_dynamic_citation_topics(cls, record: dict) -> list[dict]:
        subjects = (
            record.get("dynamic_data", {})
            .get("citation_related", {})
            .get("citation_topics", {})
            .get("subj-group", {})
            .get("subject", [])
        )
        out = []
        for subject in cls._as_list(subjects):
            if isinstance(subject, dict):
                out.append({
                    "type": subject.get("content-type"),
                    "id": subject.get("content-id"),
                    "name": subject.get("content"),
                })
        return out

    @classmethod
    def _extract_dynamic_sdg(cls, record: dict) -> list[dict]:
        raw = record.get("dynamic_data", {}).get("SDG")
        out = []
        for item in cls._as_list(raw):
            if isinstance(item, dict):
                out.append(item)
        return out

    @classmethod
    def _extract_keywords(cls, fullrecord: dict) -> list[str]:
        keywords = fullrecord.get("keywords", {}).get("keyword", [])
        return [str(x) for x in cls._as_list(keywords) if x]

    @classmethod
    def _extract_abstract(cls, fullrecord: dict) -> Optional[str]:
        raw = (
            fullrecord.get("abstracts", {})
            .get("abstract", {})
            .get("abstract_text", {})
            .get("p")
        )
        if isinstance(raw, list):
            return "\n".join(str(x) for x in raw if x)
        return str(raw) if raw else None

    def _parse_wos_record(
        self,
        record: dict,
        *,
        input_name: str,
        input_orcid: str,
        resolved_rid: Optional[str] = None,
    ) -> dict:
        uid = record.get("UID")
        static_data = record.get("static_data", {})
        summary = static_data.get("summary", {})
        fullrecord = static_data.get("fullrecord_metadata", {})
        pub_info = summary.get("pub_info", {})

        item_title, source_title = self._extract_wos_titles(summary)
        identifiers = self._extract_wos_identifiers(record)
        citations = self._extract_wos_citations(record)
        authors = self._extract_wos_authors(summary)
        matching_author = self._find_matching_author(authors, input_orcid, resolved_rid)
        addresses = self._extract_wos_addresses(fullrecord)

        all_countries = []
        all_organizations = []
        all_addresses = []
        address_map: dict[int, dict] = {}

        for address in addresses:
            spec = address.get("address_spec", {})
            country = spec.get("country")
            if country:
                all_countries.append(str(country))
            all_organizations.extend(self._organizations_from_address(address))
            full_address = spec.get("full_address")
            if full_address:
                all_addresses.append(str(full_address))
            addr_no = self._address_number(address)
            if addr_no is not None:
                address_map[addr_no] = address

        researcher_addr_nos = self._author_address_numbers(matching_author)
        researcher_countries = []
        researcher_organizations = []
        researcher_addresses = []
        for addr_no in researcher_addr_nos:
            address = address_map.get(addr_no)
            if not address:
                continue
            spec = address.get("address_spec", {})
            country = spec.get("country")
            if country:
                researcher_countries.append(str(country))
            researcher_organizations.extend(self._organizations_from_address(address))
            full_address = spec.get("full_address")
            if full_address:
                researcher_addresses.append(str(full_address))

        all_countries = sorted(self._unique_preserve(all_countries))
        all_organizations = sorted(self._unique_preserve(all_organizations))
        all_addresses = self._unique_preserve(all_addresses)
        researcher_countries = sorted(self._unique_preserve(researcher_countries))
        researcher_organizations = sorted(self._unique_preserve(researcher_organizations))
        researcher_addresses = self._unique_preserve(researcher_addresses)

        author_names = []
        author_orcids = []
        author_rids = []
        for author in authors:
            display_name = (
                author.get("display_name")
                or author.get("full_name")
                or author.get("wos_standard")
            )
            if display_name:
                author_names.append(str(display_name))
            if author.get("orcid_id"):
                author_orcids.append(str(author.get("orcid_id")))
            if author.get("r_id"):
                author_rids.append(str(author.get("r_id")))

        doctypes = summary.get("doctypes", {}).get("doctype", [])
        wos_categories = self._extract_wos_categories(fullrecord)
        citation_topics = self._extract_dynamic_citation_topics(record)
        sdg_native = self._extract_dynamic_sdg(record)

        matched_name = None
        matched_rid = None
        if matching_author:
            matched_name = (
                matching_author.get("display_name")
                or matching_author.get("full_name")
                or matching_author.get("wos_standard")
            )
            matched_rid = matching_author.get("r_id")

        out = {
            "researcher_name": input_name,
            "researcher_orcid": input_orcid,
            "researcher_id_wos": resolved_rid or matched_rid,
            "matched_author_name": matched_name,
            "matched_author_name_similarity": self._name_similarity(input_name, matched_name or ""),
            "wos_uid": uid,
            "incites_ut": str(uid).replace("WOS:", "") if uid else None,
            "title": item_title,
            "source_title": source_title,
            "publication_year": self._safe_int(pub_info.get("pubyear")),
            "publication_date": pub_info.get("sortdate") or pub_info.get("coverdate"),
            "early_access_year": self._safe_int(pub_info.get("early_access_year")),
            "publication_type": pub_info.get("pubtype"),
            "document_types_json": self._json_dumps(self._as_list(doctypes)),
            "doi": identifiers.get("doi"),
            "issn": identifiers.get("issn"),
            "eissn": identifiers.get("eissn"),
            "pmid": identifiers.get("pmid"),
            "wos_times_cited": citations.get("WOS"),
            "all_databases_times_cited": citations.get("WOK") or citations.get("ALLDB"),
            "author_count": len(authors),
            "coauthor_count": max(len(authors) - 1, 0),
            "authors_json": self._json_dumps(author_names),
            "author_orcids_json": self._json_dumps(sorted(self._unique_preserve(author_orcids))),
            "author_rids_json": self._json_dumps(sorted(self._unique_preserve(author_rids))),
            "countries_json": self._json_dumps(all_countries),
            "country_count": len(all_countries),
            "is_international_wos": int(len(all_countries) >= 2),
            "organizations_json": self._json_dumps(all_organizations),
            "organization_count": len(all_organizations),
            "addresses_json": self._json_dumps(all_addresses),
            "researcher_affiliation_countries_json": self._json_dumps(researcher_countries),
            "researcher_affiliations_json": self._json_dumps(researcher_organizations),
            "researcher_addresses_json": self._json_dumps(researcher_addresses),
            "wos_categories_json": self._json_dumps(wos_categories),
            "wos_native_citation_topics_json": self._json_dumps(citation_topics),
            "wos_native_sdg_json": self._json_dumps(sdg_native),
            "keywords_json": self._json_dumps(self._extract_keywords(fullrecord)),
            "abstract": self._extract_abstract(fullrecord),
        }

        if self.include_raw_wos_json:
            out["wos_raw_json"] = self._json_dumps(record)

        return out

    def _resolve_rid_from_wos_records(
        self,
        records: list[dict],
        orcid: str,
    ) -> tuple[Optional[str], list[str], Optional[float], list[str]]:
        rid_counter: Counter[str] = Counter()
        matched_names: Counter[str] = Counter()

        for record in records:
            summary = record.get("static_data", {}).get("summary", {})
            authors = self._extract_wos_authors(summary)
            author = self._find_matching_author(authors, orcid)
            if not author:
                continue
            rid = author.get("r_id")
            if rid:
                rid_counter[str(rid)] += 1
            name = author.get("display_name") or author.get("full_name") or author.get("wos_standard")
            if name:
                matched_names[str(name)] += 1

        if not rid_counter:
            return None, [], None, list(matched_names.keys())

        best_rid, best_count = rid_counter.most_common(1)[0]
        total_votes = sum(rid_counter.values())
        confidence = best_count / total_votes if total_votes else None
        return best_rid, list(rid_counter.keys()), confidence, list(matched_names.keys())

    def _resolve_rid_with_fallback(
        self,
        period_records: list[dict],
        orcid: str,
    ) -> tuple[Optional[str], list[str], Optional[float], list[str]]:
        result = self._resolve_rid_from_wos_records(period_records, orcid)
        if result[0]:
            return result

        self._log("  ResearcherID não apareceu no período; buscando qualquer produção do ORCID...")
        query = self._wos_query_for_orcid(orcid)
        records, _, _ = self._wos_search_records(query, page_size=20, option_view="FR")
        return self._resolve_rid_from_wos_records(records[:100], orcid)

    # ------------------------------------------------------------------
    # Web of Science Researcher API
    # ------------------------------------------------------------------

    def _get_researcher_profile(self, rid: Optional[str]) -> Optional[dict]:
        if not self.include_researcher_profile or not rid:
            return None

        return self._request_json(
            "researcher",
            "GET",
            f"{self.researcher_base_url}/researchers/{rid}",
            api_key=self.researcher_api_key,
            allow_404=True,
        )

    def _profile_common_fields(self, profile: Optional[dict]) -> dict:
        if not isinstance(profile, dict):
            return {
                "profile_h_index": None,
                "profile_times_cited": None,
                "profile_document_count": None,
                "profile_claim_status": None,
                "profile_primary_organization": None,
                "profile_primary_country": None,
            }

        h_index = self._first_scalar_by_alias(
            profile,
            {"hIndex", "h_index", "hindex", "HIndex"},
        )
        times_cited = self._first_scalar_by_alias(
            profile,
            {"timesCited", "times_cited", "totalTimesCited", "citationCount"},
        )
        document_count = self._first_scalar_by_alias(
            profile,
            {"documentCount", "document_count", "documentsCount", "publicationCount"},
        )
        claim_status = self._first_scalar_by_alias(
            profile,
            {"claimStatus", "claimed", "isClaimed"},
        )
        primary_org = self._first_scalar_by_alias(
            profile,
            {"primaryOrganization", "primaryAffiliation", "organization"},
        )
        primary_country = self._first_scalar_by_alias(
            profile,
            {"primaryCountry", "country"},
        )

        return {
            "profile_h_index": self._safe_float(h_index),
            "profile_times_cited": self._safe_float(times_cited),
            "profile_document_count": self._safe_float(document_count),
            "profile_claim_status": claim_status,
            "profile_primary_organization": primary_org if isinstance(primary_org, (str, int, float, bool)) else None,
            "profile_primary_country": primary_country if isinstance(primary_country, (str, int, float, bool)) else None,
        }

    # ------------------------------------------------------------------
    # InCites Document Level Metrics API
    # ------------------------------------------------------------------

    @classmethod
    def _incites_record_map(cls, payload: Any) -> dict[str, dict]:
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            # Compatibilidade com eventuais envelopes.
            records = (
                payload.get("Records")
                or payload.get("records")
                or payload.get("data")
                or []
            )
        else:
            records = []

        out = {}
        for record in cls._as_list(records):
            if not isinstance(record, dict):
                continue
            ut = record.get("ACCESSION_NUMBER") or record.get("UT") or record.get("ISI_LOC")
            if ut:
                out[str(ut).replace("WOS:", "")] = record
        return out

    @classmethod
    def _incites_schema_fields(cls, record: Optional[dict], schema: str) -> dict:
        if not isinstance(record, dict):
            return {
                f"incites_{schema}_subjects_json": "[]",
                f"incites_{schema}_codes_json": "[]",
                f"incites_{schema}_details_json": "[]",
                f"incites_{schema}_best_subject": None,
                f"incites_{schema}_best_code": None,
                f"incites_{schema}_best_cat_percentile": None,
                f"incites_{schema}_best_cnci": None,
                f"incites_{schema}_max_cat_percentile": None,
            }

        details = [x for x in cls._as_list(record.get("PERCENTILE")) if isinstance(x, dict)]
        subjects = [x.get("SUBJECT") for x in details if x.get("SUBJECT")]
        codes = [x.get("CODE") for x in details if x.get("CODE")]

        best = None
        for item in details:
            is_best = item.get("IS_BEST")
            if is_best is True or str(is_best).strip().lower() == "true":
                best = item
                break

        if best is None and details:
            best = max(
                details,
                key=lambda x: cls._safe_float(x.get("CATPERCENTILE"))
                if cls._safe_float(x.get("CATPERCENTILE")) is not None
                else -math.inf,
            )

        percentiles = [
            cls._safe_float(x.get("CATPERCENTILE"))
            for x in details
            if cls._safe_float(x.get("CATPERCENTILE")) is not None
        ]

        return {
            f"incites_{schema}_subjects_json": cls._json_dumps(cls._unique_preserve(subjects)),
            f"incites_{schema}_codes_json": cls._json_dumps(cls._unique_preserve(codes)),
            f"incites_{schema}_details_json": cls._json_dumps(details),
            f"incites_{schema}_best_subject": best.get("SUBJECT") if best else None,
            f"incites_{schema}_best_code": best.get("CODE") if best else None,
            f"incites_{schema}_best_cat_percentile": cls._safe_float(best.get("CATPERCENTILE")) if best else None,
            f"incites_{schema}_best_cnci": cls._safe_float(best.get("CNCI")) if best else None,
            f"incites_{schema}_max_cat_percentile": max(percentiles) if percentiles else None,
        }

    @classmethod
    def _incites_base_fields(cls, record: Optional[dict]) -> dict:
        if not isinstance(record, dict):
            return {
                "incites_available": 0,
                "incites_document_type": None,
                "incites_times_cited": None,
                "incites_journal_expected_citations": None,
                "incites_jnci": None,
                "incites_impact_factor": None,
                "incites_harmonic_mean_category_expected_citations": None,
                "incites_avg_cnci": None,
                "incites_esi_highly_cited_paper": None,
                "incites_esi_hot_paper": None,
                "incites_is_international_collab": None,
                "incites_is_institution_collab": None,
                "incites_is_industry_collab": None,
                "incites_open_access_flag": None,
                "incites_open_access_status_json": "[]",
            }

        oa = record.get("OPEN_ACCESS") or {}
        status = oa.get("STATUS", []) if isinstance(oa, dict) else []

        return {
            "incites_available": 1,
            "incites_document_type": record.get("DOCUMENT_TYPE"),
            "incites_times_cited": cls._safe_float(record.get("TIMES_CITED")),
            "incites_journal_expected_citations": cls._safe_float(record.get("JOURNAL_EXPECTED_CITATIONS")),
            "incites_jnci": cls._safe_float(record.get("JNCI")),
            "incites_impact_factor": cls._safe_float(record.get("IMPACT_FACTOR")),
            "incites_harmonic_mean_category_expected_citations": cls._safe_float(record.get("HARMEAN_CAT_EXP_CITATION")),
            "incites_avg_cnci": cls._safe_float(record.get("AVG_CNCI")),
            "incites_esi_highly_cited_paper": cls._safe_int(record.get("ESI_HIGHLY_CITED_PAPER")),
            "incites_esi_hot_paper": cls._safe_int(record.get("ESI_HOT_PAPER")),
            "incites_is_international_collab": cls._safe_int(record.get("IS_INTERNATIONAL_COLLAB")),
            "incites_is_institution_collab": cls._safe_int(record.get("IS_INSTITUTION_COLLAB")),
            "incites_is_industry_collab": cls._safe_int(record.get("IS_INDUSTRY_COLLAB")),
            "incites_open_access_flag": cls._safe_int(oa.get("OA_FLAG")) if isinstance(oa, dict) else None,
            "incites_open_access_status_json": cls._json_dumps(status),
        }

    def _fetch_incites_for_uts(self, uts: list[str]) -> dict[str, dict]:
        clean_uts = sorted(self._unique_preserve(
            str(ut).replace("WOS:", "").strip()
            for ut in uts
            if ut
        ))
        if not clean_uts:
            return {}

        merged: dict[str, dict] = defaultdict(dict)

        for schema_index, schema in enumerate(self.incites_schemas, start=1):
            self._log(
                f"  InCites schema {schema_index}/{len(self.incites_schemas)}: {schema}"
            )
            for batch in self._chunked(clean_uts, 100):
                payload = self._request_json(
                    "incites",
                    "GET",
                    f"{self.incites_base_url}/DocumentLevelMetricsByUT/json",
                    api_key=self.incites_api_key,
                    params={
                        "UT": ",".join(batch),
                        "ver": 2,
                        "schema": schema,
                        "esci": "y" if self.incites_esci else "n",
                    },
                )
                records = self._incites_record_map(payload)

                for ut in batch:
                    record = records.get(ut)
                    if schema_index == 1:
                        merged[ut].update(self._incites_base_fields(record))
                    merged[ut].update(self._incites_schema_fields(record, schema))

        # Garante que UTs sem retorno tenham todas as colunas.
        for ut in clean_uts:
            if "incites_available" not in merged[ut]:
                merged[ut].update(self._incites_base_fields(None))
            for schema in self.incites_schemas:
                key = f"incites_{schema}_details_json"
                if key not in merged[ut]:
                    merged[ut].update(self._incites_schema_fields(None, schema))

        return dict(merged)

    # ------------------------------------------------------------------
    # Pós-processamento e internacionalização
    # ------------------------------------------------------------------

    @staticmethod
    def _loads_json_list(value: Any) -> list:
        if isinstance(value, list):
            return value
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    @staticmethod
    def _mode_or_none(values: Iterable[str]) -> Optional[str]:
        counter = Counter(v for v in values if v)
        return counter.most_common(1)[0][0] if counter else None

    def _enrich_internationalization(self, publications: list[dict]) -> None:
        own_country_occurrences = []
        for pub in publications:
            own_country_occurrences.extend(
                self._loads_json_list(pub.get("researcher_affiliation_countries_json"))
            )

        home_country = self._mode_or_none(own_country_occurrences)

        for pub in publications:
            countries = self._loads_json_list(pub.get("countries_json"))
            own_countries = self._loads_json_list(
                pub.get("researcher_affiliation_countries_json")
            )

            foreign_partners = [
                country for country in countries
                if not home_country or country != home_country
            ]

            pub["home_country_inferred"] = home_country
            pub["foreign_partner_countries_json"] = self._json_dumps(
                sorted(self._unique_preserve(foreign_partners))
            )
            pub["foreign_partner_country_count"] = len(set(foreign_partners))
            pub["has_foreign_partner_inferred"] = int(bool(foreign_partners))
            pub["researcher_is_internationally_mobile_in_record"] = int(
                len(set(own_countries)) >= 2
            )

    # ------------------------------------------------------------------
    # Agregação
    # ------------------------------------------------------------------

    @staticmethod
    def _numeric_values(publications: list[dict], key: str) -> list[float]:
        out = []
        for pub in publications:
            value = ClarivateResearchMetrics._safe_float(pub.get(key))
            if value is not None:
                out.append(value)
        return out

    @classmethod
    def _summary_stats(cls, publications: list[dict], key: str, prefix: str) -> dict:
        values = cls._numeric_values(publications, key)
        if not values:
            return {
                f"{prefix}_count": 0,
                f"{prefix}_sum": None,
                f"{prefix}_mean": None,
                f"{prefix}_median": None,
                f"{prefix}_min": None,
                f"{prefix}_max": None,
                f"{prefix}_std": None,
            }
        arr = np.asarray(values, dtype=float)
        return {
            f"{prefix}_count": len(values),
            f"{prefix}_sum": float(np.sum(arr)),
            f"{prefix}_mean": float(np.mean(arr)),
            f"{prefix}_median": float(np.median(arr)),
            f"{prefix}_min": float(np.min(arr)),
            f"{prefix}_max": float(np.max(arr)),
            f"{prefix}_std": float(np.std(arr, ddof=0)),
        }

    @staticmethod
    def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if denominator in (None, 0):
            return None
        if numerator is None:
            return None
        return float(numerator) / float(denominator)

    @classmethod
    def _h_index(cls, citations: list[float]) -> int:
        values = sorted((int(max(0, x)) for x in citations), reverse=True)
        h = 0
        for i, value in enumerate(values, start=1):
            if value >= i:
                h = i
            else:
                break
        return h

    @classmethod
    def _frequency_from_json_list_column(
        cls,
        publications: list[dict],
        key: str,
    ) -> Counter:
        counter: Counter = Counter()
        for pub in publications:
            for value in cls._loads_json_list(pub.get(key)):
                if isinstance(value, dict):
                    name = value.get("name") or value.get("SUBJECT") or value.get("content")
                    if name:
                        counter[str(name)] += 1
                elif value:
                    counter[str(value)] += 1
        return counter

    @classmethod
    def _shannon_entropy(cls, counter: Counter) -> Optional[float]:
        total = sum(counter.values())
        if total <= 0:
            return None
        probs = [count / total for count in counter.values() if count > 0]
        return float(-sum(p * math.log(p, 2) for p in probs))

    @classmethod
    def _flatten_citation_report(
        cls,
        report: list[dict],
        prefix: str,
    ) -> dict:
        out = {}
        for item in report:
            if not isinstance(item, dict):
                continue
            level = str(item.get("ReportLevel", "unknown")).lower()
            level = re.sub(r"[^a-z0-9]+", "_", level).strip("_")
            base = f"{prefix}_{level}"

            mapping = {
                "TimesCitedSansSelf": "times_cited_sans_self",
                "AveragePerItem": "average_per_item",
                "TimesCited": "times_cited",
                "DedupedTimesCited": "deduped_times_cited",
                "CitingItemsSansSelf": "citing_items_sans_self",
                "AveragePerYear": "average_per_year",
                "HValue": "h_index",
            }
            for source, target in mapping.items():
                out[f"{base}_{target}"] = cls._safe_float(item.get(source))

            if isinstance(item.get("CitingYears"), dict):
                out[f"{base}_citing_years_json"] = cls._json_dumps(item["CitingYears"])

        return out

    def _aggregate_researcher(
        self,
        researcher: dict,
        publications: list[dict],
        *,
        rid: Optional[str],
        rid_candidates: list[str],
        rid_confidence: Optional[float],
        matched_names: list[str],
        profile: Optional[dict],
        citation_report_all: list[dict],
        citation_report_window: list[dict],
        start_year: int,
        end_year: int,
        wos_total_found: int,
    ) -> dict:
        row = {
            "researcher_name": researcher["name"],
            "researcher_orcid": researcher["orcid"],
            "researcher_id_wos": rid,
            "researcher_id_candidates_json": self._json_dumps(rid_candidates),
            "researcher_id_resolution_confidence": rid_confidence,
            "matched_author_names_json": self._json_dumps(matched_names),
            "period_start_year": start_year,
            "period_end_year": end_year,
            "wos_records_found": wos_total_found,
            "publication_count": len(publications),
        }

        # Mantém campos extras fornecidos na entrada, sem sobrescrever os padronizados.
        for key, value in researcher.items():
            if key not in row and key not in {"name", "orcid"}:
                row[f"input_{key}"] = value

        row.update(self._profile_common_fields(profile))
        if self.include_raw_profile_json:
            row["profile_raw_json"] = self._json_dumps(profile) if profile else None

        row.update(self._flatten_citation_report(
            citation_report_all,
            "citation_report_all",
        ))
        row.update(self._flatten_citation_report(
            citation_report_window,
            "citation_report_window",
        ))

        if not publications:
            return row

        # Cobertura InCites.
        incites_available = sum(
            1 for pub in publications if self._safe_int(pub.get("incites_available")) == 1
        )
        row["incites_publication_count"] = incites_available
        row["incites_coverage_rate"] = incites_available / len(publications)

        # Estatísticas principais de impacto.
        row.update(self._summary_stats(publications, "wos_times_cited", "wos_times_cited"))
        row.update(self._summary_stats(publications, "incites_times_cited", "incites_times_cited"))
        row.update(self._summary_stats(publications, "incites_avg_cnci", "cnci"))
        row.update(self._summary_stats(publications, "incites_jnci", "jnci"))
        row.update(self._summary_stats(publications, "incites_impact_factor", "journal_impact_factor"))
        row.update(self._summary_stats(
            publications,
            "incites_wos_best_cat_percentile",
            "wos_category_percentile",
        ))

        citations_for_h = self._numeric_values(publications, "incites_times_cited")
        if not citations_for_h:
            citations_for_h = self._numeric_values(publications, "wos_times_cited")
        row["period_h_index_computed"] = self._h_index(citations_for_h)

        # Top percentiles segundo a orientação da API InCites, na qual percentis maiores
        # representam maior impacto dentro da categoria.
        percentiles = self._numeric_values(
            publications,
            "incites_wos_best_cat_percentile",
        )
        for threshold, label in ((99, "top_1pct"), (90, "top_10pct"), (75, "top_25pct")):
            count = sum(1 for x in percentiles if x >= threshold)
            row[f"{label}_publication_count"] = count
            row[f"{label}_publication_rate"] = count / len(percentiles) if percentiles else None

        # Indicadores binários InCites.
        binary_metrics = {
            "incites_is_international_collab": "international_collaboration_incites",
            "is_international_wos": "international_collaboration_wos",
            "incites_is_institution_collab": "institutional_collaboration",
            "incites_is_industry_collab": "industry_collaboration",
            "incites_open_access_flag": "open_access",
            "incites_esi_highly_cited_paper": "esi_highly_cited_paper",
            "incites_esi_hot_paper": "esi_hot_paper",
            "has_foreign_partner_inferred": "foreign_partner_inferred",
        }
        for source_key, target in binary_metrics.items():
            values = [
                self._safe_int(pub.get(source_key))
                for pub in publications
                if self._safe_int(pub.get(source_key)) is not None
            ]
            count = sum(1 for x in values if x == 1)
            row[f"{target}_count"] = count
            row[f"{target}_rate"] = count / len(values) if values else None

        # Internacionalização detalhada por países e instituições.
        country_counter: Counter = Counter()
        foreign_partner_counter: Counter = Counter()
        own_country_counter: Counter = Counter()
        org_counter: Counter = Counter()

        for pub in publications:
            country_counter.update(self._loads_json_list(pub.get("countries_json")))
            foreign_partner_counter.update(
                self._loads_json_list(pub.get("foreign_partner_countries_json"))
            )
            own_country_counter.update(
                self._loads_json_list(pub.get("researcher_affiliation_countries_json"))
            )
            org_counter.update(self._loads_json_list(pub.get("organizations_json")))

        home_country = self._mode_or_none(own_country_counter.elements())
        row["home_country_inferred"] = home_country
        row["unique_countries_count"] = len(country_counter)
        row["countries_frequency_json"] = self._json_dumps(dict(country_counter.most_common()))
        row["unique_foreign_partner_countries_count"] = len(foreign_partner_counter)
        row["foreign_partner_countries_frequency_json"] = self._json_dumps(
            dict(foreign_partner_counter.most_common())
        )
        row["partner_country_diversity_shannon"] = self._shannon_entropy(
            foreign_partner_counter
        )
        row["researcher_affiliation_country_count_period"] = len(own_country_counter)
        row["researcher_affiliation_countries_frequency_json"] = self._json_dumps(
            dict(own_country_counter.most_common())
        )
        row["researcher_mobility_flag_period"] = int(len(own_country_counter) >= 2)
        row["unique_organizations_count"] = len(org_counter)
        row["organizations_frequency_json"] = self._json_dumps(
            dict(org_counter.most_common())
        )

        row.update(self._summary_stats(publications, "country_count", "countries_per_publication"))
        row.update(self._summary_stats(publications, "organization_count", "organizations_per_publication"))
        row.update(self._summary_stats(publications, "author_count", "authors_per_publication"))

        # Comparação impacto internacional x doméstico.
        international = [
            pub for pub in publications
            if self._safe_int(pub.get("incites_is_international_collab")) == 1
        ]
        domestic = [
            pub for pub in publications
            if self._safe_int(pub.get("incites_is_international_collab")) == 0
        ]

        int_cnci = self._numeric_values(international, "incites_avg_cnci")
        dom_cnci = self._numeric_values(domestic, "incites_avg_cnci")
        int_cit = self._numeric_values(international, "incites_times_cited")
        dom_cit = self._numeric_values(domestic, "incites_times_cited")

        row["international_cnci_mean"] = float(np.mean(int_cnci)) if int_cnci else None
        row["domestic_cnci_mean"] = float(np.mean(dom_cnci)) if dom_cnci else None
        row["international_vs_domestic_cnci_ratio"] = self._ratio(
            row["international_cnci_mean"],
            row["domestic_cnci_mean"],
        )
        row["international_minus_domestic_cnci"] = (
            row["international_cnci_mean"] - row["domestic_cnci_mean"]
            if row["international_cnci_mean"] is not None
            and row["domestic_cnci_mean"] is not None
            else None
        )

        row["international_citations_mean"] = float(np.mean(int_cit)) if int_cit else None
        row["domestic_citations_mean"] = float(np.mean(dom_cit)) if dom_cit else None
        row["international_vs_domestic_citations_ratio"] = self._ratio(
            row["international_citations_mean"],
            row["domestic_citations_mean"],
        )

        # Frequência temporal e tipologia documental.
        year_counter = Counter(
            self._safe_int(pub.get("publication_year"))
            for pub in publications
            if self._safe_int(pub.get("publication_year")) is not None
        )
        row["publications_by_year_json"] = self._json_dumps(dict(sorted(year_counter.items())))

        doctype_counter: Counter = Counter()
        source_counter: Counter = Counter()
        for pub in publications:
            doctype_counter.update(self._loads_json_list(pub.get("document_types_json")))
            if pub.get("source_title"):
                source_counter[str(pub["source_title"])] += 1
        row["document_types_frequency_json"] = self._json_dumps(dict(doctype_counter.most_common()))
        row["source_titles_frequency_json"] = self._json_dumps(dict(source_counter.most_common()))
        row["unique_source_titles_count"] = len(source_counter)

        # Agregação das taxonomias InCites.
        for schema in self.incites_schemas:
            key = f"incites_{schema}_subjects_json"
            counter = self._frequency_from_json_list_column(publications, key)
            row[f"{schema}_unique_subject_count"] = len(counter)
            row[f"{schema}_subject_frequency_json"] = self._json_dumps(
                dict(counter.most_common())
            )

        return row

    # ------------------------------------------------------------------
    # Pipeline público
    # ------------------------------------------------------------------

    def run(
        self,
        input_json: str | Path | list | dict,
        *,
        start_year: int,
        end_year: int,
        output_dir: str | Path = ".",
        researchers_filename: str = "researchers_metrics.parquet",
        publications_filename: str = "researcher_publications_metrics.parquet",
    ) -> dict[str, str]:
        start_year = int(start_year)
        end_year = int(end_year)
        if start_year > end_year:
            raise ValueError("start_year não pode ser maior que end_year.")

        researchers = self._load_input(input_json)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        all_publications: list[dict] = []
        researcher_contexts: list[dict] = []

        for idx, researcher in enumerate(researchers, start=1):
            name = researcher["name"]
            orcid = researcher["orcid"]
            self._log(
                f"\n[{idx}/{len(researchers)}] {name} | ORCID {orcid}"
            )

            query = self._wos_query_for_orcid(orcid, start_year, end_year)
            self._log(f"  Buscando produções WoS de {start_year} a {end_year}...")
            records, query_id, total_found = self._wos_search_records(query)
            self._log(f"  WoS: {total_found} registro(s) encontrado(s).")

            rid, rid_candidates, rid_confidence, matched_names = self._resolve_rid_with_fallback(
                records,
                orcid,
            )
            self._log(
                f"  ResearcherID resolvido: {rid or 'não encontrado'}"
                + (
                    f" | confiança={rid_confidence:.3f}"
                    if rid_confidence is not None
                    else ""
                )
            )

            profile = None
            if rid and self.include_researcher_profile:
                self._log("  Coletando perfil na Web of Science Researcher API...")
                profile = self._get_researcher_profile(rid)

            citation_report_all: list[dict] = []
            citation_report_window: list[dict] = []
            if self.include_citation_report and query_id and total_found < 10000:
                self._log("  Coletando Citation Report do conjunto de publicações...")
                citation_report_all = self._wos_citation_report(query_id)
                citation_report_window = self._wos_citation_report(
                    query_id,
                    start_year=start_year,
                    end_year=end_year,
                )
            elif self.include_citation_report and query_id and total_found >= 10000:
                self._log(
                    f"  Citation Report ignorado: {total_found} registros; "
                    "a API aceita conjuntos com menos de 10.000 registros."
                )

            parsed_publications = [
                self._parse_wos_record(
                    record,
                    input_name=name,
                    input_orcid=orcid,
                    resolved_rid=rid,
                )
                for record in records
            ]

            # Remove duplicatas eventuais por UID.
            unique_by_uid = {}
            for pub in parsed_publications:
                uid = pub.get("wos_uid")
                key = uid or f"__row_{len(unique_by_uid)}"
                unique_by_uid[key] = pub
            parsed_publications = list(unique_by_uid.values())

            researcher_contexts.append({
                "researcher": researcher,
                "publications": parsed_publications,
                "rid": rid,
                "rid_candidates": rid_candidates,
                "rid_confidence": rid_confidence,
                "matched_names": matched_names,
                "profile": profile,
                "citation_report_all": citation_report_all,
                "citation_report_window": citation_report_window,
                "wos_total_found": total_found,
            })
            all_publications.extend(parsed_publications)

        # InCites é coletado em lote para evitar chamadas repetidas quando a mesma
        # publicação aparece para mais de um pesquisador da lista.
        all_uts = [pub.get("incites_ut") for pub in all_publications if pub.get("incites_ut")]
        unique_uts = sorted(self._unique_preserve(all_uts))
        self._log(
            f"\nColetando métricas InCites para {len(unique_uts)} publicação(ões) única(s)..."
        )
        incites_by_ut = self._fetch_incites_for_uts(unique_uts)

        for pub in all_publications:
            ut = pub.get("incites_ut")
            pub.update(
                incites_by_ut.get(str(ut), self._incites_base_fields(None))
                if ut
                else self._incites_base_fields(None)
            )
            # Garante todas as colunas de schema mesmo sem UT/retorno.
            for schema in self.incites_schemas:
                key = f"incites_{schema}_details_json"
                if key not in pub:
                    pub.update(self._incites_schema_fields(None, schema))

        # Internacionalização e agregação por pesquisador.
        researcher_rows = []
        for context in researcher_contexts:
            pubs = context["publications"]
            self._enrich_internationalization(pubs)
            researcher_rows.append(self._aggregate_researcher(
                context["researcher"],
                pubs,
                rid=context["rid"],
                rid_candidates=context["rid_candidates"],
                rid_confidence=context["rid_confidence"],
                matched_names=context["matched_names"],
                profile=context["profile"],
                citation_report_all=context["citation_report_all"],
                citation_report_window=context["citation_report_window"],
                start_year=start_year,
                end_year=end_year,
                wos_total_found=context["wos_total_found"],
            ))

        researchers_df = self._clean_for_parquet(pd.DataFrame(researcher_rows))
        publications_df = self._clean_for_parquet(pd.DataFrame(all_publications))

        # Ordenação previsível.
        if not researchers_df.empty:
            researchers_df = researchers_df.sort_values(
                ["researcher_name", "researcher_orcid"],
                kind="stable",
            ).reset_index(drop=True)

        if not publications_df.empty:
            sort_cols = [
                col for col in (
                    "researcher_name",
                    "publication_year",
                    "title",
                )
                if col in publications_df.columns
            ]
            publications_df = publications_df.sort_values(
                sort_cols,
                ascending=[True, False, True][:len(sort_cols)],
                kind="stable",
                na_position="last",
            ).reset_index(drop=True)

        researchers_path = output_dir / researchers_filename
        publications_path = output_dir / publications_filename

        researchers_df.to_parquet(researchers_path, index=False, engine="pyarrow")
        publications_df.to_parquet(publications_path, index=False, engine="pyarrow")

        self._log("\nConcluído.")
        self._log(f"  Pesquisadores: {researchers_path}")
        self._log(f"  Publicações:   {publications_path}")

        return {
            "researchers_parquet": str(researchers_path),
            "publications_parquet": str(publications_path),
        }
