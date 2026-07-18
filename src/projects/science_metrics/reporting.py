"""Step de materialização dos relatórios tabulares e do grafo final de colaboração.

A etapa consolida somente a produção atribuída aos pesquisadores selecionados, calcula
indicadores agregados e cria relações ``COLLABORATES_WITH`` entre entidades canônicas.
Os resultados permanecem consultáveis diretamente no ArcadeDB.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from websensors_flow.result import StepResult
from websensors_flow.step import PipelineStep

from projects.science_metrics.project_config import build_arcadedb_client, reporting_config
from projects.science_metrics.utils import ensure_dir, h_index, json_dumps, json_loads, stable_id, to_float, to_int


def _mean(values: list[float | int | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


class BuildScienceMetricsReportsStep(PipelineStep):
    """Materialize production indicators and a canonical collaboration graph in ArcadeDB."""

    def execute(self, input: Any, context) -> StepResult:
        """Documentação da função pública ``execute`` do pipeline Science Metrics."""
        db = build_arcadedb_client(context)
        cfg = reporting_config(context)
        base_country = str(cfg.get("base_country") or "BR").upper()

        researchers = db.query("SELECT FROM researcher_entities WHERE selected = true")
        coauthors = db.query("SELECT FROM coauthor_entities")
        works = db.query("SELECT FROM works")

        researcher_by_alias: dict[str, dict[str, Any]] = {}
        researcher_by_entity: dict[str, dict[str, Any]] = {}
        for row in researchers:
            entity_id = str(row.get("entity_id") or "")
            researcher_by_entity[entity_id] = row
            for raw_id in json_loads(row.get("raw_author_ids_json"), []) or []:
                researcher_by_alias[str(raw_id)] = row

        coauthor_by_alias = {str(row.get("raw_author_id") or ""): row for row in coauthors if row.get("raw_author_id")}
        selected_aliases = set(researcher_by_alias)
        group_works: list[dict[str, Any]] = []
        production_rows: list[dict[str, Any]] = []
        pair_evidence: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"work_ids": set(), "years": [], "citations": 0}
        )

        participant_rids: dict[str, str] = {}
        participant_is_group: dict[str, bool] = {}
        for row in researchers:
            entity_id = str(row.get("entity_id") or "")
            if entity_id and row.get("@rid"):
                participant_rids[entity_id] = str(row["@rid"])
                participant_is_group[entity_id] = True
        for row in coauthors:
            entity_id = str(row.get("entity_id") or "")
            if entity_id and row.get("@rid"):
                participant_rids[entity_id] = str(row["@rid"])
                participant_is_group[entity_id] = False

        for work in works:
            authorships = json_loads(work.get("authorships_json"), []) or []
            author_ids = {str(item.get("author_id") or "") for item in authorships}
            if not (author_ids & selected_aliases):
                continue
            group_works.append(work)
            canonical_participants: dict[str, dict[str, Any]] = {}
            group_author_names: list[str] = []
            coauthor_names: list[str] = []
            countries: set[str] = set()
            institutions: set[str] = set()
            unresolved_participants = 0

            for authorship in authorships:
                raw_id = str(authorship.get("author_id") or "")
                display_name = str(authorship.get("author_name") or raw_id)
                if raw_id in researcher_by_alias:
                    entity = researcher_by_alias[raw_id]
                    entity_id = str(entity.get("entity_id") or "")
                    canonical_participants[entity_id] = entity
                    group_author_names.append(str(entity.get("canonical_name") or display_name))
                    country = str(entity.get("primary_country") or "").upper()
                    institution = str(entity.get("primary_institution_name") or "")
                elif raw_id in coauthor_by_alias:
                    entity = coauthor_by_alias[raw_id]
                    entity_id = str(entity.get("entity_id") or "")
                    canonical_participants[entity_id] = entity
                    coauthor_names.append(str(entity.get("display_name") or display_name))
                    country = str(entity.get("primary_country") or "").upper()
                    institution = str(entity.get("primary_institution_name") or "")
                else:
                    unresolved_participants += 1
                    coauthor_names.append(display_name)
                    country = ""
                    institution = ""
                if country:
                    countries.add(country)
                if institution:
                    institutions.add(institution)

            international = any(country != base_country for country in countries)
            country_evidence_complete = unresolved_participants == 0 and bool(countries)
            row = {
                "work_id": str(work.get("openalex_id") or ""),
                "title": str(work.get("title") or ""),
                "doi": str(work.get("doi") or ""),
                "publication_year": to_int(work.get("publication_year")),
                "publication_date": str(work.get("publication_date") or ""),
                "type": str(work.get("type") or ""),
                "raw_type": str(work.get("raw_type") or ""),
                "cited_by_count": to_int(work.get("cited_by_count")),
                "fwci": to_float(work.get("fwci")),
                "citation_percentile": to_float(work.get("citation_percentile")),
                "is_in_top_1_percent": bool(work.get("is_in_top_1_percent")),
                "is_in_top_10_percent": bool(work.get("is_in_top_10_percent")),
                "is_oa": bool(work.get("is_oa")),
                "oa_status": str(work.get("oa_status") or ""),
                "source_id": str(work.get("source_id") or ""),
                "source_name": str(work.get("source_name") or ""),
                "source_type": str(work.get("source_type") or ""),
                "source_h_index": to_int(work.get("source_h_index")),
                "source_i10_index": to_int(work.get("source_i10_index")),
                "source_2yr_mean_citedness": to_float(work.get("source_2yr_mean_citedness")),
                "primary_topic_id": str(work.get("primary_topic_id") or ""),
                "primary_topic_name": str(work.get("primary_topic_name") or ""),
                "international_category": "internacional" if international else "nacional",
                "is_international": international,
                "base_country": base_country,
                "countries_json": json_dumps(sorted(countries)),
                "institutions_json": json_dumps(sorted(institutions)),
                "group_authors_json": json_dumps(sorted(set(group_author_names))),
                "coauthors_json": json_dumps(sorted(set(coauthor_names))),
                "participant_entity_ids_json": json_dumps(sorted(canonical_participants)),
                "unresolved_participants": unresolved_participants,
                "country_evidence_complete": country_evidence_complete,
                "topics_json": str(work.get("topics_json") or "[]"),
                "keywords_json": str(work.get("keywords_json") or "[]"),
            }
            db.create_document("report_production", row)
            production_rows.append(row)

            participant_ids = sorted(canonical_participants)
            for index, left in enumerate(participant_ids):
                for right in participant_ids[index + 1 :]:
                    if not (participant_is_group.get(left, False) or participant_is_group.get(right, False)):
                        continue
                    key = tuple(sorted((left, right)))
                    evidence = pair_evidence[key]
                    evidence["work_ids"].add(row["work_id"])
                    if row["publication_year"]:
                        evidence["years"].append(row["publication_year"])
                    evidence["citations"] += row["cited_by_count"]

        collaboration_edges = 0
        for (left, right), evidence in pair_evidence.items():
            left_rid = participant_rids.get(left)
            right_rid = participant_rids.get(right)
            if not left_rid or not right_rid:
                continue
            years = evidence["years"]
            db.create_edge(
                "COLLABORATES_WITH",
                left_rid,
                right_rid,
                {
                    "works_count": len(evidence["work_ids"]),
                    "work_ids_json": json_dumps(sorted(evidence["work_ids"])),
                    "first_year": min(years) if years else 0,
                    "last_year": max(years) if years else 0,
                    "citations_sum": int(evidence["citations"]),
                },
            )
            collaboration_edges += 1

        citations = [row["cited_by_count"] for row in production_rows]
        fwci_values = [row["fwci"] for row in production_rows if row["fwci"] is not None]
        source_impact_values = [
            row["source_2yr_mean_citedness"] for row in production_rows if row["source_2yr_mean_citedness"] is not None
        ]
        source_h_values = [row["source_h_index"] for row in production_rows if row["source_h_index"] > 0]
        national_count = sum(1 for row in production_rows if not row["is_international"])
        international_count = sum(1 for row in production_rows if row["is_international"])
        open_access_count = sum(1 for row in production_rows if row["is_oa"])
        top10_count = sum(1 for row in production_rows if row["is_in_top_10_percent"])
        n_works = len(production_rows)
        countries = sorted(
            {
                country
                for row in production_rows
                for country in (json_loads(row.get("countries_json"), []) or [])
                if country
            }
        )
        institutions = sorted(
            {
                institution
                for row in production_rows
                for institution in (json_loads(row.get("institutions_json"), []) or [])
                if institution
            }
        )
        years = [row["publication_year"] for row in production_rows if row["publication_year"]]
        summary = {
            "summary_id": stable_id("summary", [db.database]),
            "database_name": db.database,
            "base_country": base_country,
            "publications": n_works,
            "citations_total": sum(citations),
            "group_h_index": h_index(citations),
            "mean_fwci": _mean(fwci_values),
            "mean_source_2yr_mean_citedness": _mean(source_impact_values),
            "mean_source_h_index": _mean(source_h_values),
            "open_access_publications": open_access_count,
            "open_access_percent": (100.0 * open_access_count / n_works) if n_works else 0.0,
            "top_10_percent_publications": top10_count,
            "top_10_percent_share": (100.0 * top10_count / n_works) if n_works else 0.0,
            "national_publications": national_count,
            "international_publications": international_count,
            "national_share": (100.0 * national_count / n_works) if n_works else 0.0,
            "international_share": (100.0 * international_count / n_works) if n_works else 0.0,
            "researchers": len(researchers),
            "external_coauthors": len(coauthors),
            "collaboration_edges": collaboration_edges,
            "countries_count": len(countries),
            "institutions_count": len(institutions),
            "first_publication_year": min(years) if years else 0,
            "last_publication_year": max(years) if years else 0,
            "countries_json": json_dumps(countries),
            "institutions_json": json_dumps(institutions),
        }
        db.create_document("report_group_summary", summary)

        output_dir = ensure_dir(context.step_config.get("output_dir") or "./outputs/science_metrics")
        summary_path = Path(output_dir) / f"{db.database}_summary.json"
        summary_path.write_text(json_dumps(summary), encoding="utf-8")

        sql_summary = "SELECT FROM report_group_summary"
        sql_production = "SELECT FROM report_production ORDER BY publication_year DESC"
        cypher_graph = (
            "MATCH (r:researcher_entities)-[e:COLLABORATES_WITH]-(n) "
            "WHERE r.selected = true RETURN r,e,n"
        )
        access_text = (
            f"ArcadeDB Studio: {db.studio_url}\n"
            f"Banco: {db.database}\n"
            f"Usuário: {db.username}\n"
            f"Resumo SQL: {sql_summary}\n"
            f"Produção SQL: {sql_production}\n"
            f"Grafo OpenCypher: {cypher_graph}"
        )
        print("\n=== WebSensors Science Metrics concluído ===")
        print(access_text)
        print(
            f"Estatísticas: {n_works} produções, {sum(citations)} citações, "
            f"h-index do grupo {summary['group_h_index']}, {collaboration_edges} colaborações."
        )

        output = dict(input or {})
        output["reporting"] = summary
        return StepResult(
            output=output,
            has_output=True,
            text=f"Relatórios materializados no ArcadeDB.\n{access_text}",
            metrics={
                "publications": n_works,
                "citations_total": sum(citations),
                "group_h_index": summary["group_h_index"],
                "mean_fwci": float(summary["mean_fwci"] or 0.0),
                "national_publications": national_count,
                "international_publications": international_count,
                "collaboration_edges": collaboration_edges,
                "researchers": len(researchers),
                "external_coauthors": len(coauthors),
            },
            params={"base_country": base_country},
            metadata={
                "arcadedb_studio": db.studio_url,
                "database": db.database,
                "sql_summary": sql_summary,
                "sql_production": sql_production,
                "opencypher_graph": cypher_graph,
            },
            artifacts={"group_summary": str(summary_path)},
        )
