"""Normalização dos JSONs do OpenAlex e step de ingestão da pipeline.

Este módulo converte respostas ricas e aninhadas do OpenAlex em registros adequados à
camada bruta do ArcadeDB. O JSON original continua armazenado para auditoria, enquanto
campos recorrentes são promovidos a propriedades consultáveis de autores, instituições
e trabalhos.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from websensors_flow.result import MetricRecord, StepResult
from websensors_flow.step import PipelineStep

from projects.science_metrics.project_config import (
    arcadedb_config,
    build_arcadedb_client,
    build_openalex_client,
    group_config,
    openalex_config,
)
from projects.science_metrics.schema import create_schema
from projects.science_metrics.utils import (
    dedupe_strings,
    json_dumps,
    normalize_name,
    short_openalex_id,
    stable_id,
    to_float,
    to_int,
)


def normalize_seeds(researchers: list[Any]) -> list[dict[str, Any]]:
    """Normaliza a lista de pesquisadores declarada no YAML e gera identificadores estáveis para as sementes."""
    result: list[dict[str, Any]] = []
    for index, value in enumerate(researchers, start=1):
        if isinstance(value, str):
            item = {"name": value}
        elif isinstance(value, dict):
            item = dict(value)
        else:
            continue
        name = str(item.get("name") or item.get("query") or "").strip()
        if not name:
            continue
        item["name"] = name
        item["query"] = str(item.get("query") or name).strip()
        item["seed_id"] = str(item.get("seed_id") or stable_id("seed", [str(index), normalize_name(name)]))
        if item.get("country_hint"):
            item["country_hint"] = str(item["country_hint"]).upper()
        result.append(item)
    return result


def _embedded_institution(institution: dict[str, Any]) -> dict[str, Any]:
    institution_id = str(institution.get("id") or institution.get("openalex_id") or "")
    name = str(institution.get("display_name") or institution.get("name") or "").strip()
    country = str(institution.get("country_code") or institution.get("country") or "").upper()
    if not institution_id:
        institution_id = stable_id("LOCAL_INST", [normalize_name(name), country])
    return {
        "openalex_id": institution_id,
        "display_name": name or institution_id,
        "country_code": country,
        "type": str(institution.get("type") or ""),
        "lineage": list(institution.get("lineage") or []),
        "ror": str(institution.get("ror") or ""),
        "homepage_url": str(institution.get("homepage_url") or ""),
        "image_url": str(institution.get("image_url") or ""),
        "raw_json": json_dumps(institution),
    }


def normalize_authorships(work: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Normaliza as autorias de um trabalho e extrai autores e instituições encontrados no JSON original."""
    work_id = str(work.get("id") or "")
    normalized: list[dict[str, Any]] = []
    authors: dict[str, dict[str, Any]] = {}
    institutions: dict[str, dict[str, Any]] = {}

    for index, authorship in enumerate(work.get("authorships") or []):
        if not isinstance(authorship, dict):
            continue
        raw_author = authorship.get("author") or {}
        author_id = str(raw_author.get("id") or "")
        author_name = str(raw_author.get("display_name") or "").strip()
        if not author_id:
            author_id = stable_id("ANON_AUTHOR", [work_id, str(index), normalize_name(author_name)])
        author_record = {
            "openalex_id": author_id,
            "display_name": author_name or author_id,
            "orcid": str(raw_author.get("orcid") or ""),
            "works_count": to_int(raw_author.get("works_count")),
            "cited_by_count": to_int(raw_author.get("cited_by_count")),
            "is_anonymous": author_id.startswith("ANON_AUTHOR_"),
            "candidate_seeds_json": "[]",
            "last_known_institutions_json": "[]",
            "affiliations_json": "[]",
            "ids_json": json_dumps(raw_author.get("ids") or {}),
            "summary_stats_json": json_dumps(raw_author.get("summary_stats") or {}),
            "raw_json": json_dumps(raw_author),
        }
        authors.setdefault(author_id, author_record)

        normalized_institutions: list[dict[str, Any]] = []
        for raw_institution in authorship.get("institutions") or []:
            if not isinstance(raw_institution, dict):
                continue
            institution_record = _embedded_institution(raw_institution)
            institutions.setdefault(institution_record["openalex_id"], institution_record)
            normalized_institutions.append(
                {
                    "id": institution_record["openalex_id"],
                    "name": institution_record["display_name"],
                    "country": institution_record["country_code"],
                    "type": institution_record["type"],
                    "lineage": institution_record["lineage"],
                }
            )

        normalized.append(
            {
                "author_id": author_id,
                "author_name": author_name or author_id,
                "author_position": str(authorship.get("author_position") or ""),
                "is_corresponding": bool(authorship.get("is_corresponding")),
                "countries": dedupe_strings(authorship.get("countries") or []),
                "institutions": normalized_institutions,
                "raw_author_id": str(raw_author.get("id") or ""),
            }
        )
    return normalized, authors, institutions


def _source_record(source: dict[str, Any]) -> dict[str, Any]:
    summary = source.get("summary_stats") or {}
    return {
        "id": str(source.get("id") or ""),
        "display_name": str(source.get("display_name") or ""),
        "type": str(source.get("type") or ""),
        "issn_l": str(source.get("issn_l") or ""),
        "issn": list(source.get("issn") or []),
        "is_oa": bool(source.get("is_oa")),
        "is_in_doaj": bool(source.get("is_in_doaj")),
        "host_organization": str(source.get("host_organization") or ""),
        "homepage_url": str(source.get("homepage_url") or ""),
        "works_count": to_int(source.get("works_count")),
        "cited_by_count": to_int(source.get("cited_by_count")),
        "h_index": to_int(summary.get("h_index")),
        "i10_index": to_int(summary.get("i10_index")),
        "two_year_mean_citedness": to_float(summary.get("2yr_mean_citedness")),
    }


def normalize_work(work: dict[str, Any], source_details: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Converte um trabalho do OpenAlex em propriedades consultáveis e preserva o JSON bruto para auditoria."""
    work_id = str(work.get("id") or "")
    authorships, authors, institutions = normalize_authorships(work)
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    source_id = str(source.get("id") or "")
    source_info = dict(_source_record(source))
    if source_id and source_id in source_details:
        source_info.update(_source_record(source_details[source_id]))

    oa = work.get("open_access") or {}
    citation_percentile = work.get("citation_normalized_percentile") or {}
    primary_topic = work.get("primary_topic") or {}
    best_oa_location = work.get("best_oa_location") or {}
    row = {
        "openalex_id": work_id,
        "title": str(work.get("display_name") or work.get("title") or ""),
        "doi": str(work.get("doi") or ""),
        "publication_year": to_int(work.get("publication_year")),
        "publication_date": str(work.get("publication_date") or ""),
        "type": str(work.get("type") or ""),
        "raw_type": str(primary_location.get("raw_type") or work.get("type_crossref") or work.get("type") or ""),
        "language": str(work.get("language") or ""),
        "cited_by_count": to_int(work.get("cited_by_count")),
        "fwci": to_float(work.get("fwci")),
        "citation_percentile": to_float(citation_percentile.get("value")),
        "is_in_top_1_percent": bool(citation_percentile.get("is_in_top_1_percent")),
        "is_in_top_10_percent": bool(citation_percentile.get("is_in_top_10_percent")),
        "is_retracted": bool(work.get("is_retracted")),
        "is_paratext": bool(work.get("is_paratext")),
        "is_oa": bool(oa.get("is_oa")),
        "oa_status": str(oa.get("oa_status") or ""),
        "oa_url": str(oa.get("oa_url") or best_oa_location.get("landing_page_url") or ""),
        "any_repository_has_fulltext": bool(oa.get("any_repository_has_fulltext")),
        "source_id": source_id,
        "source_name": source_info.get("display_name") or "",
        "source_type": source_info.get("type") or "",
        "source_h_index": to_int(source_info.get("h_index")),
        "source_i10_index": to_int(source_info.get("i10_index")),
        "source_2yr_mean_citedness": to_float(source_info.get("two_year_mean_citedness")),
        "primary_topic_id": str(primary_topic.get("id") or ""),
        "primary_topic_name": str(primary_topic.get("display_name") or ""),
        "authorships_json": json_dumps(authorships),
        "topics_json": json_dumps(work.get("topics") or []),
        "keywords_json": json_dumps(work.get("keywords") or []),
        "concepts_json": json_dumps(work.get("concepts") or []),
        "locations_json": json_dumps(work.get("locations") or []),
        "referenced_works_json": json_dumps(work.get("referenced_works") or []),
        "related_works_json": json_dumps(work.get("related_works") or []),
        "counts_by_year_json": json_dumps(work.get("counts_by_year") or []),
        "grants_json": json_dumps(work.get("grants") or []),
        "sustainable_development_goals_json": json_dumps(work.get("sustainable_development_goals") or []),
        "mesh_json": json_dumps(work.get("mesh") or []),
        "locations_count": to_int(work.get("locations_count")),
        "raw_json": json_dumps(work),
    }
    return row, authors, institutions


def normalize_author(author: dict[str, Any], candidate_seeds: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Converte um perfil de autor do OpenAlex em um registro normalizado da camada bruta."""
    summary = author.get("summary_stats") or {}
    return {
        "openalex_id": str(author.get("id") or ""),
        "display_name": str(author.get("display_name") or ""),
        "display_name_alternatives_json": json_dumps(author.get("display_name_alternatives") or []),
        "orcid": str(author.get("orcid") or ""),
        "works_count": to_int(author.get("works_count")),
        "cited_by_count": to_int(author.get("cited_by_count")),
        "h_index": to_int(summary.get("h_index")),
        "i10_index": to_int(summary.get("i10_index")),
        "two_year_mean_citedness": to_float(summary.get("2yr_mean_citedness")),
        "is_anonymous": False,
        "candidate_seeds_json": json_dumps(candidate_seeds or []),
        "last_known_institutions_json": json_dumps(author.get("last_known_institutions") or []),
        "affiliations_json": json_dumps(author.get("affiliations") or []),
        "ids_json": json_dumps(author.get("ids") or {}),
        "raw_json": json_dumps(author),
    }


class IngestDataStep(PipelineStep):
    """Resolve OpenAlex candidates and ingest normalized raw vertices into ArcadeDB."""

    def execute(self, input: Any, context) -> StepResult:
        """Documentação da função pública ``execute`` do pipeline Science Metrics."""
        group = group_config(context)
        oa_cfg = openalex_config(context)
        arcade_cfg = arcadedb_config(context)
        seeds = normalize_seeds(list(group.get("researchers") or []))
        if not seeds:
            raise ValueError("Configure pelo menos um pesquisador em pipeline.params.group.researchers.")

        db = build_arcadedb_client(context)
        openalex = build_openalex_client(context)
        db.wait_until_ready(
            attempts=int(arcade_cfg.get("readiness_attempts") or 15),
            delay_seconds=float(arcade_cfg.get("readiness_delay_seconds") or 1),
        )
        recreate = bool(arcade_cfg.get("recreate_on_run", True))
        db.recreate_database(drop_existing=recreate)
        create_schema(db)

        top_n = int(oa_cfg.get("top_n_candidates") or 5)
        start_year = oa_cfg.get("start_year")
        end_year = oa_cfg.get("end_year")
        max_pages = int(oa_cfg.get("max_pages_per_candidate") or 10)

        author_profiles: dict[str, dict[str, Any]] = {}
        author_seed_links: dict[str, list[dict[str, Any]]] = defaultdict(list)
        raw_works: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        metric_records: list[MetricRecord] = []

        for seed in seeds:
            if seed.get("openalex_id"):
                candidates = [openalex.get_author(str(seed["openalex_id"]))]
            else:
                candidates = openalex.search_authors(seed["query"], top_n=top_n)
            if not candidates:
                warnings.append(f"Nenhum candidato encontrado no OpenAlex para {seed['name']}.")
                continue

            for rank, candidate in enumerate(candidates, start=1):
                author_id = str(candidate.get("id") or "")
                if not author_id:
                    continue
                # Exact author endpoint provides richer profile metadata when search returns a projection.
                try:
                    profile = openalex.get_author(author_id)
                except Exception:
                    profile = candidate
                author_profiles[author_id] = profile
                author_seed_links[author_id].append(
                    {
                        "seed_id": seed["seed_id"],
                        "seed_name": seed["name"],
                        "query": seed["query"],
                        "rank": rank,
                        "relevance_score": to_float(candidate.get("relevance_score")),
                    }
                )
                works = openalex.fetch_works_for_author(
                    author_id,
                    start_year=int(start_year) if start_year else None,
                    end_year=int(end_year) if end_year else None,
                    max_pages=max_pages,
                )
                for work in works:
                    work_id = str(work.get("id") or "")
                    if work_id and (work_id not in raw_works or len(json_dumps(work)) > len(json_dumps(raw_works[work_id]))):
                        raw_works[work_id] = work
                metric_records.append(
                    MetricRecord(
                        name=f"candidate:{short_openalex_id(author_id)}",
                        metrics={"works_collected": len(works), "candidate_rank": rank},
                        params={"seed_name": seed["name"], "author_name": profile.get("display_name") or ""},
                        metadata={"author_id": author_id},
                    )
                )

        # Enrich unique source metadata before normalizing works.
        source_ids: list[str] = []
        for work in raw_works.values():
            source_id = str((((work.get("primary_location") or {}).get("source") or {}).get("id")) or "")
            if source_id:
                source_ids.append(source_id)
        source_details: dict[str, dict[str, Any]] = {}
        max_sources = int(oa_cfg.get("max_sources_to_enrich") or 250)
        for source_id in dedupe_strings(source_ids)[:max_sources]:
            try:
                source_details[source_id] = openalex.get_source(source_id)
            except Exception as exc:
                warnings.append(f"Não foi possível enriquecer o veículo {source_id}: {exc}")

        normalized_works: dict[str, dict[str, Any]] = {}
        normalized_authors: dict[str, dict[str, Any]] = {}
        normalized_institutions: dict[str, dict[str, Any]] = {}
        for work in raw_works.values():
            work_row, embedded_authors, embedded_institutions = normalize_work(work, source_details)
            if work_row["openalex_id"]:
                normalized_works[work_row["openalex_id"]] = work_row
            for author_id, author_row in embedded_authors.items():
                normalized_authors.setdefault(author_id, author_row)
            for institution_id, institution_row in embedded_institutions.items():
                normalized_institutions.setdefault(institution_id, institution_row)

        for author_id, profile in author_profiles.items():
            normalized_authors[author_id] = normalize_author(profile, author_seed_links.get(author_id))
            for institution in profile.get("last_known_institutions") or []:
                if isinstance(institution, dict):
                    row = _embedded_institution(institution)
                    normalized_institutions.setdefault(row["openalex_id"], row)
            for affiliation in profile.get("affiliations") or []:
                institution = (affiliation or {}).get("institution") or {}
                if institution:
                    row = _embedded_institution(institution)
                    normalized_institutions.setdefault(row["openalex_id"], row)

        # Optional richer institution profiles. Embedded metadata remains the fallback.
        max_institutions = int(oa_cfg.get("max_institutions_to_enrich") or 500)
        institution_ids = [item for item in normalized_institutions if short_openalex_id(item).startswith("I")]
        for institution_id in institution_ids[:max_institutions]:
            try:
                raw = openalex.get_institution(institution_id)
            except Exception as exc:
                warnings.append(f"Não foi possível enriquecer a instituição {institution_id}: {exc}")
                continue
            normalized_institutions[institution_id] = {
                "openalex_id": str(raw.get("id") or institution_id),
                "display_name": str(raw.get("display_name") or normalized_institutions[institution_id].get("display_name") or ""),
                "display_name_acronyms_json": json_dumps(raw.get("display_name_acronyms") or []),
                "display_name_alternatives_json": json_dumps(raw.get("display_name_alternatives") or []),
                "country_code": str((raw.get("geo") or {}).get("country_code") or raw.get("country_code") or "").upper(),
                "country": str((raw.get("geo") or {}).get("country") or ""),
                "city": str((raw.get("geo") or {}).get("city") or ""),
                "region": str((raw.get("geo") or {}).get("region") or ""),
                "latitude": to_float((raw.get("geo") or {}).get("latitude")),
                "longitude": to_float((raw.get("geo") or {}).get("longitude")),
                "type": str(raw.get("type") or ""),
                "ror": str(raw.get("ror") or ""),
                "homepage_url": str(raw.get("homepage_url") or ""),
                "image_url": str(raw.get("image_url") or ""),
                "works_count": to_int(raw.get("works_count")),
                "cited_by_count": to_int(raw.get("cited_by_count")),
                "lineage_json": json_dumps(raw.get("lineage") or []),
                "ids_json": json_dumps(raw.get("ids") or {}),
                "roles_json": json_dumps(raw.get("roles") or []),
                "repositories_json": json_dumps(raw.get("repositories") or []),
                "raw_json": json_dumps(raw),
            }

        author_rids: dict[str, str] = {}
        institution_rids: dict[str, str] = {}
        work_rids: dict[str, str] = {}
        for author_id, row in normalized_authors.items():
            author_rids[author_id] = db.create_vertex("authors", row)
        for institution_id, row in normalized_institutions.items():
            institution_rids[institution_id] = db.create_vertex("institutions", row)
        for work_id, row in normalized_works.items():
            work_rids[work_id] = db.create_vertex("works", row)

        output = {
            "database_name": db.database,
            "studio_url": db.studio_url,
            "seeds": seeds,
            "counts": {
                "researcher_seeds": len(seeds),
                "candidate_profiles": len(author_profiles),
                "authors": len(normalized_authors),
                "institutions": len(normalized_institutions),
                "works": len(normalized_works),
                "sources_enriched": len(source_details),
            },
        }
        return StepResult(
            output=output,
            has_output=True,
            text=(
                f"Ingestão concluída no banco '{db.database}': {len(normalized_authors)} autores, "
                f"{len(normalized_institutions)} instituições e {len(normalized_works)} trabalhos normalizados."
            ),
            metrics={
                "researcher_seeds": len(seeds),
                "candidate_profiles": len(author_profiles),
                "authors": len(normalized_authors),
                "institutions": len(normalized_institutions),
                "works": len(normalized_works),
                "sources_enriched": len(source_details),
            },
            params={"top_n_candidates": top_n, "start_year": start_year or 0, "end_year": end_year or 0},
            metadata={"database": db.database, "arcadedb_url": db.studio_url},
            warnings=warnings,
            metric_records=metric_records,
        )
