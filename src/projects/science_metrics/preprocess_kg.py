"""Step que transforma os registros normalizados em um grafo de conhecimento bruto.

A etapa cria relações explícitas de autoria, afiliação, candidatura, associação
institucional e citação. Nenhuma decisão canônica de identidade é tomada aqui: o objetivo
é preservar a evidência estrutural que será usada pelos steps de modelagem posteriores.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from websensors_flow.result import StepResult
from websensors_flow.step import PipelineStep

from projects.science_metrics.ingest_data import normalize_seeds
from projects.science_metrics.project_config import build_arcadedb_client, group_config
from projects.science_metrics.utils import json_dumps, json_loads


class PreprocessKnowledgeGraphStep(PipelineStep):
    """Convert normalized raw vertices into an explicit raw knowledge graph."""

    def execute(self, input: Any, context) -> StepResult:
        """Documentação da função pública ``execute`` do pipeline Science Metrics."""
        db = build_arcadedb_client(context)
        seeds = normalize_seeds(list(group_config(context).get("researchers") or []))
        authors = db.query("SELECT FROM authors")
        institutions = db.query("SELECT FROM institutions")
        works = db.query("SELECT FROM works")

        author_rids = {str(row.get("openalex_id")): str(row.get("@rid")) for row in authors if row.get("openalex_id") and row.get("@rid")}
        institution_rids = {
            str(row.get("openalex_id")): str(row.get("@rid")) for row in institutions if row.get("openalex_id") and row.get("@rid")
        }
        work_rids = {str(row.get("openalex_id")): str(row.get("@rid")) for row in works if row.get("openalex_id") and row.get("@rid")}

        seed_rids: dict[str, str] = {}
        for seed in seeds:
            seed_rids[seed["seed_id"]] = db.create_vertex(
                "researcher_seeds",
                {
                    "seed_id": seed["seed_id"],
                    "name": seed["name"],
                    "query": seed["query"],
                    "openalex_id_hint": str(seed.get("openalex_id") or ""),
                    "orcid_hint": str(seed.get("orcid") or ""),
                    "institution_hint": str(seed.get("institution_hint") or ""),
                    "country_hint": str(seed.get("country_hint") or ""),
                    "raw_config_json": json_dumps(seed),
                },
            )

        candidate_edges = 0
        for author in authors:
            author_rid = str(author.get("@rid") or "")
            if not author_rid:
                continue
            for candidate in json_loads(author.get("candidate_seeds_json"), []) or []:
                seed_id = str(candidate.get("seed_id") or "")
                seed_rid = seed_rids.get(seed_id)
                if not seed_rid:
                    continue
                db.create_edge(
                    "CANDIDATE_FOR",
                    author_rid,
                    seed_rid,
                    {
                        "rank": int(candidate.get("rank") or 0),
                        "relevance_score": candidate.get("relevance_score"),
                        "query": str(candidate.get("query") or ""),
                    },
                )
                candidate_edges += 1

        authored_edges = 0
        associated_edges = 0
        citation_edges = 0
        affiliation_evidence: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"work_ids": set(), "years": [], "positions": set(), "countries": set()}
        )

        for work in works:
            work_id = str(work.get("openalex_id") or "")
            work_rid = work_rids.get(work_id)
            if not work_rid:
                continue
            year = int(work.get("publication_year") or 0)
            authorships = json_loads(work.get("authorships_json"), []) or []
            institution_to_authors: dict[str, list[str]] = defaultdict(list)
            for authorship in authorships:
                author_id = str(authorship.get("author_id") or "")
                author_rid = author_rids.get(author_id)
                if not author_rid:
                    continue
                db.create_edge(
                    "AUTHORED",
                    author_rid,
                    work_rid,
                    {
                        "author_position": str(authorship.get("author_position") or ""),
                        "is_corresponding": bool(authorship.get("is_corresponding")),
                        "countries_json": json_dumps(authorship.get("countries") or []),
                    },
                )
                authored_edges += 1
                for institution in authorship.get("institutions") or []:
                    institution_id = str(institution.get("id") or "")
                    if not institution_id or institution_id not in institution_rids:
                        continue
                    evidence = affiliation_evidence[(author_id, institution_id)]
                    evidence["work_ids"].add(work_id)
                    if year:
                        evidence["years"].append(year)
                    evidence["positions"].add(str(authorship.get("author_position") or ""))
                    evidence["countries"].update(authorship.get("countries") or [])
                    institution_to_authors[institution_id].append(author_id)

            for institution_id, institution_authors in institution_to_authors.items():
                db.create_edge(
                    "ASSOCIATED_WITH_INSTITUTION",
                    work_rid,
                    institution_rids[institution_id],
                    {"authors_json": json_dumps(sorted(set(institution_authors)))},
                )
                associated_edges += 1

            for referenced_id in json_loads(work.get("referenced_works_json"), []) or []:
                target_rid = work_rids.get(str(referenced_id))
                if target_rid:
                    db.create_edge("CITES", work_rid, target_rid, {})
                    citation_edges += 1

        affiliation_edges = 0
        for (author_id, institution_id), evidence in affiliation_evidence.items():
            author_rid = author_rids.get(author_id)
            institution_rid = institution_rids.get(institution_id)
            if not author_rid or not institution_rid:
                continue
            years = [int(value) for value in evidence["years"] if value]
            db.create_edge(
                "AFFILIATED_WITH",
                author_rid,
                institution_rid,
                {
                    "work_count": len(evidence["work_ids"]),
                    "work_ids_json": json_dumps(sorted(evidence["work_ids"])),
                    "first_year": min(years) if years else 0,
                    "last_year": max(years) if years else 0,
                    "positions_json": json_dumps(sorted(evidence["positions"])),
                    "countries_json": json_dumps(sorted(evidence["countries"])),
                },
            )
            affiliation_edges += 1

        total_edges = candidate_edges + authored_edges + associated_edges + citation_edges + affiliation_edges
        output = dict(input or {})
        output["raw_kg"] = {
            "candidate_edges": candidate_edges,
            "authored_edges": authored_edges,
            "affiliation_edges": affiliation_edges,
            "associated_institution_edges": associated_edges,
            "citation_edges": citation_edges,
        }
        return StepResult(
            output=output,
            has_output=True,
            text=f"KG bruta criada no ArcadeDB com {total_edges} relações explícitas.",
            metrics={
                "candidate_edges": candidate_edges,
                "authored_edges": authored_edges,
                "affiliation_edges": affiliation_edges,
                "associated_institution_edges": associated_edges,
                "citation_edges": citation_edges,
                "total_edges": total_edges,
            },
        )
