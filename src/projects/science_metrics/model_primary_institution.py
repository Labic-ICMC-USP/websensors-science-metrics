"""Step e utilitários para materializar a instituição principal de pesquisadores.

A inferência é executada sobre as entidades já resolvidas, usando o histórico de trabalhos
e afiliações. O resultado é persistido como uma entidade derivada, sem substituir as
instituições brutas coletadas no OpenAlex.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from websensors_flow.result import StepResult
from websensors_flow.step import PipelineStep

from projects.science_metrics.institution_model import infer_principal_institution
from projects.science_metrics.project_config import build_arcadedb_client, modeling_config
from projects.science_metrics.utils import json_dumps, json_loads, normalize_name, stable_id


def _fallback_last_known(raw_authors: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Documentação da função pública ``_fallback_last_known`` do pipeline Science Metrics."""
    counter: Counter[tuple[str, str, str]] = Counter()
    payloads: dict[tuple[str, str, str], dict[str, Any]] = {}
    for author in raw_authors:
        for institution in json_loads(author.get("last_known_institutions_json"), []) or []:
            if not isinstance(institution, dict):
                continue
            institution_id = str(institution.get("id") or "")
            name = str(institution.get("display_name") or institution.get("name") or "").strip()
            country = str(institution.get("country_code") or institution.get("country") or "").upper()
            key = (institution_id, normalize_name(name), country)
            if not institution_id and not name:
                continue
            counter[key] += 1
            payloads[key] = {
                "openalex_id": institution_id,
                "name": name or institution_id,
                "country": country,
                "score": 0.25,
                "works_count": 0,
                "work_ids": [],
                "years": [],
            }
    if not counter:
        return None
    key, _ = counter.most_common(1)[0]
    return payloads[key]


def ensure_principal_institution(db, cache: dict[str, str], primary: dict[str, Any], *, method: str, confidence: float, candidates: list[dict[str, Any]]) -> tuple[str, str]:
    """Reutiliza ou cria uma entidade de instituição principal e registra as evidências que deram origem à inferência."""
    openalex_id = str(primary.get("openalex_id") or "")
    name = str(primary.get("name") or openalex_id or "Unknown institution")
    country = str(primary.get("country") or "").upper()
    principal_id = stable_id("principal_inst", [openalex_id or normalize_name(name), country])
    if principal_id not in cache:
        cache[principal_id] = db.create_vertex(
            "principal_institutions",
            {
                "principal_id": principal_id,
                "openalex_id": openalex_id,
                "display_name": name,
                "country_code": country,
                "inference_method": method,
                "confidence": float(confidence),
                "evidence_works": int(primary.get("works_count") or 0),
                "candidate_ranking_json": json_dumps(candidates),
            },
        )
    return principal_id, cache[principal_id]


class InferPrincipalInstitutionStep(PipelineStep):
    """Infer the principal institution of each resolved researcher using their own publication history."""

    def execute(self, input: Any, context) -> StepResult:
        """Documentação da função pública ``execute`` do pipeline Science Metrics."""
        db = build_arcadedb_client(context)
        cfg = dict(modeling_config(context).get("institution") or {})
        fuzzy_threshold = float(cfg.get("fuzzy_threshold", 92))
        recency_decay = float(cfg.get("recency_decay", 0.86))

        entities = db.query("SELECT FROM researcher_entities")
        authors = db.query("SELECT FROM authors")
        works = db.query("SELECT FROM works")
        institutions = db.query("SELECT FROM institutions")
        author_by_id = {str(row.get("openalex_id")): row for row in authors}
        institution_rids = {
            str(row.get("openalex_id")): str(row.get("@rid"))
            for row in institutions
            if row.get("openalex_id") and row.get("@rid")
        }

        normalized_works = [
            {
                "id": row.get("openalex_id"),
                "publication_year": row.get("publication_year"),
                "authorships": json_loads(row.get("authorships_json"), []) or [],
            }
            for row in works
        ]
        principal_cache: dict[str, str] = {}
        inferred = 0
        fallback_count = 0
        missing = 0

        for entity in entities:
            entity_rid = str(entity.get("@rid") or "")
            entity_id = str(entity.get("entity_id") or "")
            raw_ids = set(json_loads(entity.get("raw_author_ids_json"), []) or [])
            if not entity_rid or not raw_ids:
                continue
            inference = infer_principal_institution(
                author_ids=raw_ids,
                works=normalized_works,
                fuzzy_threshold=fuzzy_threshold,
                recency_decay=recency_decay,
            )
            primary = inference.get("primary")
            method = str(inference.get("method") or "frequency_recency_fuzzy_v1")
            confidence = float(inference.get("confidence") or 0.0)
            candidates = list(inference.get("candidates") or [])
            if not primary:
                primary = _fallback_last_known([author_by_id[item] for item in raw_ids if item in author_by_id])
                if primary:
                    fallback_count += 1
                    method = "last_known_institution_fallback_v1"
                    confidence = 0.25
                    candidates = [primary]
            if not primary:
                missing += 1
                continue

            principal_id, principal_rid = ensure_principal_institution(
                db,
                principal_cache,
                primary,
                method=method,
                confidence=confidence,
                candidates=candidates,
            )
            db.create_edge(
                "HAS_PRIMARY_INSTITUTION",
                entity_rid,
                principal_rid,
                {
                    "method": method,
                    "confidence": confidence,
                    "evidence_works": int(inference.get("evidence_works") or primary.get("works_count") or 0),
                },
            )
            raw_institution_id = str(primary.get("openalex_id") or "")
            if raw_institution_id in institution_rids:
                db.create_edge("DERIVED_FROM_INSTITUTION", principal_rid, institution_rids[raw_institution_id], {})
            db.update(
                "researcher_entities",
                "entity_id",
                entity_id,
                {
                    "primary_institution_id": principal_id,
                    "primary_institution_name": str(primary.get("name") or ""),
                    "primary_country": str(primary.get("country") or "").upper(),
                    "primary_institution_confidence": confidence,
                    "primary_institution_method": method,
                },
            )
            inferred += 1

        output = dict(input or {})
        output["principal_institutions"] = {"inferred": inferred, "fallback": fallback_count, "missing": missing}
        return StepResult(
            output=output,
            has_output=True,
            text=f"Instituição principal inferida para {inferred} entidades de pesquisador.",
            metrics={
                "researcher_entities": len(entities),
                "principal_institutions_inferred": inferred,
                "fallback_inferences": fallback_count,
                "missing_institutions": missing,
                "principal_institution_vertices": len(principal_cache),
            },
            params={"fuzzy_threshold": fuzzy_threshold, "recency_decay": recency_decay},
        )
