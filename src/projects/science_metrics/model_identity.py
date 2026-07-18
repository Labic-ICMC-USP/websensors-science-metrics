"""Step de modelagem responsável pela resolução canônica dos pesquisadores-semente.

O step aplica a resolução de entidades aos candidatos coletados, cria os vértices
``researcher_entities`` e registra tanto os merges quanto as evidências que justificam
cada decisão. Perfis sem ambiguidade também recebem uma entidade canônica própria.
"""

from __future__ import annotations

from typing import Any

from websensors_flow.result import StepResult
from websensors_flow.step import PipelineStep

from projects.science_metrics.entity_resolution import resolve_candidates
from projects.science_metrics.ingest_data import normalize_seeds
from projects.science_metrics.project_config import build_arcadedb_client, group_config, modeling_config
from projects.science_metrics.utils import json_dumps, json_loads


class ResolveResearcherIdentityStep(PipelineStep):
    """Merge candidate OpenAlex profiles into evidence-backed researcher entities."""

    def execute(self, input: Any, context) -> StepResult:
        """Documentação da função pública ``execute`` do pipeline Science Metrics."""
        db = build_arcadedb_client(context)
        cfg = dict(modeling_config(context).get("entity_resolution") or {})
        all_authors = db.query("SELECT FROM authors")
        candidate_authors = [row for row in all_authors if json_loads(row.get("candidate_seeds_json"), [])]
        works = db.query("SELECT FROM works")
        seeds = normalize_seeds(list(group_config(context).get("researchers") or []))

        resolution = resolve_candidates(authors=candidate_authors, works=works, seeds=seeds, config=cfg)
        author_rids = {
            str(row.get("openalex_id")): str(row.get("@rid"))
            for row in candidate_authors
            if row.get("openalex_id") and row.get("@rid")
        }
        seed_rids = {
            str(row.get("seed_id")): str(row.get("@rid"))
            for row in db.query("SELECT FROM researcher_seeds")
            if row.get("seed_id") and row.get("@rid")
        }

        entity_rids: dict[str, str] = {}
        for entity in resolution["entities"]:
            entity_rids[entity["entity_id"]] = db.create_vertex(
                "researcher_entities",
                {
                    "entity_id": entity["entity_id"],
                    "canonical_name": entity["canonical_name"],
                    "raw_author_ids_json": json_dumps(entity["raw_author_ids"]),
                    "orcids_json": json_dumps(entity["orcids"]),
                    "seed_ids_json": json_dumps(entity["seed_ids"]),
                    "works_count": int(entity["works_count"]),
                    "cited_by_count_max": int(entity["cited_by_count_max"]),
                    "countries_json": json_dumps(entity["countries"]),
                    "institution_names_json": json_dumps(entity["institution_names"]),
                    "selected": bool(entity["selected"]),
                    "selected_for_seeds_json": json_dumps(entity["selected_for_seeds"]),
                    "selection_score": float(entity["selection_score"]),
                    "selection_ambiguous": bool(entity["selection_ambiguous"]),
                    "resolution_method": "multi_evidence_union_find_v1",
                    "merge_threshold": float(resolution["merge_threshold"]),
                },
            )

        resolved_edges = 0
        for author_id, entity_id in resolution["author_to_entity"].items():
            if author_id in author_rids and entity_id in entity_rids:
                db.create_edge("RESOLVED_AS", author_rids[author_id], entity_rids[entity_id], {})
                resolved_edges += 1

        evidence_edges = 0
        for evidence in resolution["evidence"]:
            left_rid = author_rids.get(evidence["left_id"])
            right_rid = author_rids.get(evidence["right_id"])
            if not left_rid or not right_rid:
                continue
            db.create_edge(
                "SAME_AS_EVIDENCE",
                left_rid,
                right_rid,
                {
                    "score": float(evidence["score"]),
                    "decision": evidence["decision"],
                    "components_json": json_dumps(evidence["components"]),
                },
            )
            evidence_edges += 1

        selection_edges = 0
        ambiguous = 0
        missing = 0
        for selection in resolution["seed_selection"]:
            entity_rid = entity_rids.get(selection.get("selected_entity_id") or "")
            seed_rid = seed_rids.get(selection.get("seed_id") or "")
            if not entity_rid or not seed_rid:
                missing += 1
                continue
            db.create_edge(
                "REPRESENTS_RESEARCHER",
                entity_rid,
                seed_rid,
                {
                    "selection_score": float(selection.get("score") or 0.0),
                    "ambiguous": bool(selection.get("ambiguous")),
                    "rankings_json": json_dumps(selection.get("rankings") or []),
                },
            )
            selection_edges += 1
            ambiguous += int(bool(selection.get("ambiguous")))

        output = dict(input or {})
        output["identity_resolution"] = {
            "entities": len(resolution["entities"]),
            "selected": sum(1 for item in resolution["entities"] if item["selected"]),
            "ambiguous_selections": ambiguous,
        }
        warnings = []
        if ambiguous:
            warnings.append(
                f"{ambiguous} pesquisador(es) tiveram seleção ambígua entre candidatos; consulte REPRESENTS_RESEARCHER.rankings_json."
            )
        if missing:
            warnings.append(f"{missing} pesquisador(es) não puderam ser associados a uma entidade selecionada.")

        return StepResult(
            output=output,
            has_output=True,
            text=(
                f"Resolução de identidade criou {len(resolution['entities'])} entidades canônicas, "
                f"com {selection_edges} pesquisador(es) selecionado(s) para o grupo."
            ),
            metrics={
                "candidate_profiles": len(candidate_authors),
                "researcher_entities": len(resolution["entities"]),
                "selected_entities": sum(1 for item in resolution["entities"] if item["selected"]),
                "resolved_as_edges": resolved_edges,
                "same_as_evidence_edges": evidence_edges,
                "ambiguous_selections": ambiguous,
                "missing_selections": missing,
            },
            params={
                "merge_threshold": float(resolution["merge_threshold"]),
                "evidence_threshold": float(resolution["evidence_threshold"]),
            },
            warnings=warnings,
        )
