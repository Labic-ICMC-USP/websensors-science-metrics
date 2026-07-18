"""Step de enriquecimento de coautores externos ao grupo principal.

Cada coautor é consultado novamente no OpenAlex para que sua instituição e país principais
sejam inferidos a partir de sua própria produção recente. Os trabalhos extras são usados
como evidência e não entram nos indicadores de produção do grupo analisado.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from websensors_flow.result import MetricRecord, StepResult
from websensors_flow.step import PipelineStep

from projects.science_metrics.institution_model import infer_principal_institution
from projects.science_metrics.model_primary_institution import ensure_principal_institution
from projects.science_metrics.project_config import build_arcadedb_client, build_openalex_client, modeling_config, openalex_config
from projects.science_metrics.utils import json_dumps, json_loads, short_openalex_id, stable_id


class EnrichCoauthorsStep(PipelineStep):
    """Fetch each external coauthor's own recent production and infer principal institution/country."""

    def execute(self, input: Any, context) -> StepResult:
        """Documentação da função pública ``execute`` do pipeline Science Metrics."""
        db = build_arcadedb_client(context)
        openalex = build_openalex_client(context)
        oa_cfg = openalex_config(context)
        inst_cfg = dict(modeling_config(context).get("institution") or {})
        recent_limit = int(oa_cfg.get("coauthor_recent_works") or 10)
        max_external = int(oa_cfg.get("max_external_coauthors") or 0)
        fuzzy_threshold = float(inst_cfg.get("fuzzy_threshold", 92))
        recency_decay = float(inst_cfg.get("recency_decay", 0.86))

        researchers = db.query("SELECT FROM researcher_entities WHERE selected = true")
        selected_aliases: set[str] = set()
        for entity in researchers:
            selected_aliases.update(json_loads(entity.get("raw_author_ids_json"), []) or [])

        works = db.query("SELECT FROM works")
        raw_authors = db.query("SELECT FROM authors")
        author_rids = {
            str(row.get("openalex_id")): str(row.get("@rid"))
            for row in raw_authors
            if row.get("openalex_id") and row.get("@rid")
        }
        institution_rids = {
            str(row.get("openalex_id")): str(row.get("@rid"))
            for row in db.query("SELECT FROM institutions")
            if row.get("openalex_id") and row.get("@rid")
        }

        group_works: list[dict[str, Any]] = []
        local_works_by_author: dict[str, list[dict[str, Any]]] = defaultdict(list)
        external_names: dict[str, str] = {}
        for row in works:
            authorships = json_loads(row.get("authorships_json"), []) or []
            author_ids = {str(item.get("author_id") or "") for item in authorships}
            if not (author_ids & selected_aliases):
                continue
            normalized_work = {
                "id": row.get("openalex_id"),
                "publication_year": row.get("publication_year"),
                "authorships": authorships,
            }
            group_works.append(normalized_work)
            for authorship in authorships:
                author_id = str(authorship.get("author_id") or "")
                if not author_id or author_id in selected_aliases:
                    continue
                external_names[author_id] = str(authorship.get("author_name") or author_id)
                local_works_by_author[author_id].append(normalized_work)

        external_ids = sorted(external_names)
        if max_external > 0:
            external_ids = external_ids[:max_external]

        principal_cache = {
            str(row.get("principal_id")): str(row.get("@rid"))
            for row in db.query("SELECT FROM principal_institutions")
            if row.get("principal_id") and row.get("@rid")
        }
        enriched = 0
        remote_enriched = 0
        local_fallback = 0
        missing = 0
        metric_records: list[MetricRecord] = []
        warnings: list[str] = []

        for author_id in external_ids:
            recent_works: list[dict[str, Any]] = []
            evidence_source = "group_work_fallback"
            is_openalex_author = short_openalex_id(author_id).startswith("A") and not author_id.startswith("ANON_AUTHOR_")
            if is_openalex_author:
                try:
                    recent_works = openalex.fetch_recent_works_for_author(author_id, limit=recent_limit)
                    if recent_works:
                        evidence_source = "openalex_recent_own_works"
                        remote_enriched += 1
                except Exception as exc:
                    warnings.append(f"Falha ao enriquecer coautor {external_names[author_id]} ({author_id}): {exc}")
            works_for_inference = recent_works or local_works_by_author[author_id]
            if not recent_works:
                local_fallback += 1
            inference = infer_principal_institution(
                author_ids={author_id},
                works=works_for_inference,
                fuzzy_threshold=fuzzy_threshold,
                recency_decay=recency_decay,
            )
            primary = inference.get("primary")
            entity_id = stable_id("coauthor", [author_id])
            coauthor_props = {
                "entity_id": entity_id,
                "openalex_id": author_id if is_openalex_author else "",
                "display_name": external_names[author_id],
                "raw_author_id": author_id,
                "primary_institution_id": "",
                "primary_institution_name": "",
                "primary_country": "",
                "institution_confidence": float(inference.get("confidence") or 0.0),
                "institution_method": str(inference.get("method") or "frequency_recency_fuzzy_v1"),
                "evidence_source": evidence_source,
                "recent_work_ids_json": json_dumps([str(work.get("id") or "") for work in recent_works]),
                "recent_works_count": len(recent_works),
                "group_works_count": len(local_works_by_author[author_id]),
            }
            if primary:
                principal_id, principal_rid = ensure_principal_institution(
                    db,
                    principal_cache,
                    primary,
                    method=str(inference.get("method") or "frequency_recency_fuzzy_v1"),
                    confidence=float(inference.get("confidence") or 0.0),
                    candidates=list(inference.get("candidates") or []),
                )
                coauthor_props.update(
                    {
                        "primary_institution_id": principal_id,
                        "primary_institution_name": str(primary.get("name") or ""),
                        "primary_country": str(primary.get("country") or "").upper(),
                    }
                )
            else:
                missing += 1

            coauthor_rid = db.create_vertex("coauthor_entities", coauthor_props)
            raw_author_rid = author_rids.get(author_id)
            if raw_author_rid:
                db.create_edge("RESOLVED_AS_COAUTHOR", raw_author_rid, coauthor_rid, {})
            if primary:
                principal_rid = principal_cache[coauthor_props["primary_institution_id"]]
                db.create_edge(
                    "HAS_PRIMARY_INSTITUTION",
                    coauthor_rid,
                    principal_rid,
                    {
                        "method": coauthor_props["institution_method"],
                        "confidence": coauthor_props["institution_confidence"],
                        "evidence_source": evidence_source,
                    },
                )
                raw_institution_id = str(primary.get("openalex_id") or "")
                if raw_institution_id in institution_rids:
                    db.create_edge("DERIVED_FROM_INSTITUTION", principal_rid, institution_rids[raw_institution_id], {})
            enriched += 1
            metric_records.append(
                MetricRecord(
                    name=f"coauthor:{short_openalex_id(author_id)}",
                    metrics={
                        "recent_works": len(recent_works),
                        "group_works": len(local_works_by_author[author_id]),
                        "institution_confidence": float(inference.get("confidence") or 0.0),
                    },
                    params={"name": external_names[author_id], "evidence_source": evidence_source},
                    metadata={"author_id": author_id, "primary_country": coauthor_props["primary_country"]},
                )
            )

        output = dict(input or {})
        output["coauthors"] = {
            "total_external": len(external_names),
            "processed": enriched,
            "remote_enriched": remote_enriched,
            "local_fallback": local_fallback,
        }
        return StepResult(
            output=output,
            has_output=True,
            text=(
                f"{enriched} coautores externos foram classificados; {remote_enriched} usaram suas próprias "
                f"produções recentes no OpenAlex para inferir instituição e país principais."
            ),
            metrics={
                "group_works": len(group_works),
                "external_coauthors_found": len(external_names),
                "external_coauthors_processed": enriched,
                "remote_recent_works_enrichment": remote_enriched,
                "local_fallback": local_fallback,
                "missing_principal_institution": missing,
            },
            params={"coauthor_recent_works": recent_limit, "max_external_coauthors": max_external},
            warnings=warnings,
            metric_records=metric_records,
        )
