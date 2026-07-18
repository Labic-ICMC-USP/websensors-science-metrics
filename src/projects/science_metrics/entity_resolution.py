"""Funções de engenharia de atributos e resolução de identidade de pesquisadores.

A estratégia atual é deliberadamente explicável: cada par de candidatos recebe um score
composto por nome, ORCID, trabalhos, DOIs, coautores, instituições, tópicos, país e origem
da busca. Pares acima do limiar são agrupados por Union-Find e mantêm suas evidências.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rapidfuzz.fuzz import token_set_ratio

from projects.science_metrics.utils import json_loads, normalize_name, short_openalex_id, stable_id, to_float, to_int


@dataclass
class CandidateFeatures:
    """Conjunto de atributos derivados de um perfil candidato usado pelo cálculo de similaridade entre autores."""
    author_id: str
    name: str
    orcid: str
    works: set[str]
    dois: set[str]
    coauthors: set[str]
    institutions: set[str]
    institution_names: set[str]
    countries: set[str]
    topics: set[str]
    seed_ids: set[str]
    best_rank: int
    rank_by_seed: dict[str, int]
    works_count: int
    cited_by_count: int


class UnionFind:
    """Estrutura disjoint-set usada para transformar pares considerados equivalentes em componentes de identidade."""
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: str) -> str:
        """Retorna o representante canônico do conjunto contendo o valor informado, aplicando compressão de caminho."""
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        """Une os componentes de dois candidatos considerados equivalentes pelo modelo de resolução."""
        root_l = self.find(left)
        root_r = self.find(right)
        if root_l == root_r:
            return
        if self.rank[root_l] < self.rank[root_r]:
            root_l, root_r = root_r, root_l
        self.parent[root_r] = root_l
        if self.rank[root_l] == self.rank[root_r]:
            self.rank[root_l] += 1


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _containment(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _normalized_orcid(value: Any) -> str:
    text = str(value or "").strip().lower().replace("https://orcid.org/", "")
    return text.rstrip("/")


def build_candidate_features(authors: list[dict[str, Any]], works: list[dict[str, Any]]) -> dict[str, CandidateFeatures]:
    """Constrói, para cada candidato, as evidências necessárias à comparação de identidade a partir de autores e trabalhos."""
    work_map: dict[str, set[str]] = defaultdict(set)
    doi_map: dict[str, set[str]] = defaultdict(set)
    coauthor_map: dict[str, set[str]] = defaultdict(set)
    institution_map: dict[str, set[str]] = defaultdict(set)
    institution_name_map: dict[str, set[str]] = defaultdict(set)
    country_map: dict[str, set[str]] = defaultdict(set)
    topic_map: dict[str, set[str]] = defaultdict(set)

    for work in works:
        work_id = str(work.get("openalex_id") or work.get("id") or "")
        doi = str(work.get("doi") or "").lower().strip()
        topics = json_loads(work.get("topics_json"), []) or work.get("topics") or []
        topic_ids: set[str] = set()
        for topic in topics:
            if isinstance(topic, dict):
                topic_id = str(topic.get("id") or topic.get("display_name") or topic.get("name") or "")
            else:
                topic_id = str(topic or "")
            if topic_id:
                topic_ids.add(topic_id)

        authorships = json_loads(work.get("authorships_json"), []) or work.get("authorships") or []
        normalized_authors: list[str] = []
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author_id = str(authorship.get("author_id") or (authorship.get("author") or {}).get("id") or "")
            if author_id:
                normalized_authors.append(author_id)

        for author_id in normalized_authors:
            if work_id:
                work_map[author_id].add(work_id)
            if doi:
                doi_map[author_id].add(doi)
            coauthor_map[author_id].update(item for item in normalized_authors if item != author_id)
            topic_map[author_id].update(topic_ids)

        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author_id = str(authorship.get("author_id") or (authorship.get("author") or {}).get("id") or "")
            if not author_id:
                continue
            for institution in authorship.get("institutions") or []:
                if not isinstance(institution, dict):
                    continue
                institution_id = str(institution.get("id") or institution.get("openalex_id") or "")
                institution_name = normalize_name(institution.get("display_name") or institution.get("name"))
                country = str(institution.get("country_code") or institution.get("country") or "").upper()
                if institution_id:
                    institution_map[author_id].add(institution_id)
                if institution_name:
                    institution_name_map[author_id].add(institution_name)
                if country:
                    country_map[author_id].add(country)

    result: dict[str, CandidateFeatures] = {}
    for row in authors:
        author_id = str(row.get("openalex_id") or row.get("id") or "")
        if not author_id:
            continue
        seed_candidates = json_loads(row.get("candidate_seeds_json"), []) or []
        seed_ids = {str(item.get("seed_id") or "") for item in seed_candidates if isinstance(item, dict) and item.get("seed_id")}
        ranks = [to_int(item.get("rank"), 999999) for item in seed_candidates if isinstance(item, dict)]
        rank_by_seed = {str(item.get("seed_id")): to_int(item.get("rank"), 999999) for item in seed_candidates if isinstance(item, dict) and item.get("seed_id")}
        last_institutions = json_loads(row.get("last_known_institutions_json"), []) or []
        institutions = set(institution_map[author_id])
        institution_names = set(institution_name_map[author_id])
        countries = set(country_map[author_id])
        for institution in last_institutions:
            if not isinstance(institution, dict):
                continue
            institution_id = str(institution.get("id") or "")
            institution_name = normalize_name(institution.get("display_name") or institution.get("name"))
            country = str(institution.get("country_code") or institution.get("country") or "").upper()
            if institution_id:
                institutions.add(institution_id)
            if institution_name:
                institution_names.add(institution_name)
            if country:
                countries.add(country)

        result[author_id] = CandidateFeatures(
            author_id=author_id,
            name=str(row.get("display_name") or row.get("name") or author_id),
            orcid=_normalized_orcid(row.get("orcid")),
            works=work_map[author_id],
            dois=doi_map[author_id],
            coauthors=coauthor_map[author_id],
            institutions=institutions,
            institution_names=institution_names,
            countries=countries,
            topics=topic_map[author_id],
            seed_ids=seed_ids,
            best_rank=min(ranks, default=999999),
            rank_by_seed=rank_by_seed,
            works_count=to_int(row.get("works_count")),
            cited_by_count=to_int(row.get("cited_by_count")),
        )
    return result


def pair_similarity(left: CandidateFeatures, right: CandidateFeatures, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calcula o score explicável entre dois candidatos e retorna também a contribuição de cada evidência."""
    cfg = dict(config or {})
    name_similarity = token_set_ratio(normalize_name(left.name), normalize_name(right.name)) / 100.0
    work_overlap = max(_jaccard(left.works, right.works), _containment(left.works, right.works))
    doi_overlap = max(_jaccard(left.dois, right.dois), _containment(left.dois, right.dois))
    coauthor_overlap = _jaccard(left.coauthors, right.coauthors)
    institution_overlap = max(
        _jaccard(left.institutions, right.institutions),
        _jaccard(left.institution_names, right.institution_names),
    )
    topic_overlap = _jaccard(left.topics, right.topics)
    country_overlap = _jaccard(left.countries, right.countries)
    same_seed = bool(left.seed_ids & right.seed_ids)
    exact_orcid = bool(left.orcid and right.orcid and left.orcid == right.orcid)
    conflicting_orcid = bool(left.orcid and right.orcid and left.orcid != right.orcid)

    if exact_orcid:
        score = 1.0
    else:
        weights = {
            "name": float(cfg.get("weight_name", 0.25)),
            "work": float(cfg.get("weight_work_overlap", 0.28)),
            "doi": float(cfg.get("weight_doi_overlap", 0.17)),
            "coauthor": float(cfg.get("weight_coauthor_overlap", 0.12)),
            "institution": float(cfg.get("weight_institution_overlap", 0.08)),
            "topic": float(cfg.get("weight_topic_overlap", 0.05)),
            "country": float(cfg.get("weight_country_overlap", 0.03)),
            "same_seed": float(cfg.get("weight_same_seed", 0.02)),
        }
        numerator = (
            weights["name"] * name_similarity
            + weights["work"] * work_overlap
            + weights["doi"] * doi_overlap
            + weights["coauthor"] * coauthor_overlap
            + weights["institution"] * institution_overlap
            + weights["topic"] * topic_overlap
            + weights["country"] * country_overlap
            + weights["same_seed"] * (1.0 if same_seed else 0.0)
        )
        denominator = sum(weights.values()) or 1.0
        score = numerator / denominator

        # Shared exact production is stronger than noisy affiliation metadata.
        if (work_overlap >= 0.5 or doi_overlap >= 0.5) and name_similarity >= 0.75:
            score = max(score, 0.84 + 0.12 * max(work_overlap, doi_overlap))
        elif name_similarity >= 0.96 and coauthor_overlap >= 0.35:
            score = max(score, 0.78 + 0.15 * coauthor_overlap)

    if not exact_orcid and name_similarity < 0.55:
        score = min(score, 0.60)
    if conflicting_orcid:
        score = min(score, float(cfg.get("conflicting_orcid_score_cap", 0.44)))

    components = {
        "name_similarity": round(name_similarity, 6),
        "work_overlap": round(work_overlap, 6),
        "doi_overlap": round(doi_overlap, 6),
        "coauthor_overlap": round(coauthor_overlap, 6),
        "institution_overlap": round(institution_overlap, 6),
        "topic_overlap": round(topic_overlap, 6),
        "country_overlap": round(country_overlap, 6),
        "same_seed": same_seed,
        "exact_orcid": exact_orcid,
        "conflicting_orcid": conflicting_orcid,
    }
    return {"score": round(max(0.0, min(1.0, score)), 6), "components": components}


def resolve_candidates(
    *,
    authors: list[dict[str, Any]],
    works: list[dict[str, Any]],
    seeds: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve candidatos em entidades canônicas, preserva evidências de pares e seleciona a entidade mais provável por pesquisador-semente."""
    cfg = dict(config or {})
    merge_threshold = float(cfg.get("merge_threshold", 0.72))
    evidence_threshold = float(cfg.get("evidence_edge_threshold", 0.55))
    allow_cross_seed = bool(cfg.get("allow_cross_seed_merge", True))
    ambiguity_margin = float(cfg.get("selection_ambiguity_margin", 0.08))

    features = build_candidate_features(authors, works)
    ids = sorted(features)
    union_find = UnionFind(ids)
    evidence: list[dict[str, Any]] = []

    for index, left_id in enumerate(ids):
        left = features[left_id]
        for right_id in ids[index + 1 :]:
            right = features[right_id]
            if not allow_cross_seed and left.seed_ids and right.seed_ids and not (left.seed_ids & right.seed_ids):
                continue
            comparison = pair_similarity(left, right, cfg)
            score = float(comparison["score"])
            if score >= evidence_threshold:
                evidence.append(
                    {
                        "left_id": left_id,
                        "right_id": right_id,
                        "score": score,
                        "decision": "merge" if score >= merge_threshold else "review",
                        "components": comparison["components"],
                    }
                )
            if score >= merge_threshold:
                union_find.union(left_id, right_id)

    grouped: dict[str, list[str]] = defaultdict(list)
    for author_id in ids:
        grouped[union_find.find(author_id)].append(author_id)

    entities: list[dict[str, Any]] = []
    author_to_entity: dict[str, str] = {}
    for member_ids in grouped.values():
        member_ids = sorted(member_ids)
        members = [features[item] for item in member_ids]
        canonical = max(members, key=lambda item: (item.works_count, item.cited_by_count, -item.best_rank, len(item.name)))
        entity_id = stable_id("researcher", member_ids)
        entity = {
            "entity_id": entity_id,
            "canonical_name": canonical.name,
            "raw_author_ids": member_ids,
            "orcids": sorted({item.orcid for item in members if item.orcid}),
            "seed_ids": sorted({seed_id for item in members for seed_id in item.seed_ids}),
            "works_count": len({work for item in members for work in item.works}),
            "cited_by_count_max": max((item.cited_by_count for item in members), default=0),
            "countries": sorted({country for item in members for country in item.countries}),
            "institution_names": sorted({name for item in members for name in item.institution_names}),
            "selected": False,
            "selected_for_seeds": [],
            "selection_score": 0.0,
            "selection_ambiguous": False,
        }
        entities.append(entity)
        for author_id in member_ids:
            author_to_entity[author_id] = entity_id

    entity_by_id = {entity["entity_id"]: entity for entity in entities}
    seed_selection: list[dict[str, Any]] = []
    for seed in seeds:
        seed_id = str(seed.get("seed_id") or "")
        seed_name = str(seed.get("name") or seed.get("query") or "")
        configured_author_id = str(seed.get("openalex_id") or "")
        configured_orcid = _normalized_orcid(seed.get("orcid"))
        institution_hint = normalize_name(seed.get("institution_hint"))
        country_hint = str(seed.get("country_hint") or "").upper()

        candidate_entities = [entity for entity in entities if seed_id in entity["seed_ids"]]
        rankings: list[dict[str, Any]] = []
        for entity in candidate_entities:
            member_features = [features[author_id] for author_id in entity["raw_author_ids"]]
            name_score = max(
                (token_set_ratio(normalize_name(seed_name), normalize_name(item.name)) / 100.0 for item in member_features),
                default=0.0,
            )
            best_rank = min((item.rank_by_seed.get(seed_id, 999999) for item in member_features), default=999999)
            rank_score = 1.0 / max(1, best_rank)
            institution_score = 0.0
            if institution_hint:
                institution_score = max(
                    (token_set_ratio(institution_hint, candidate_name) / 100.0 for item in member_features for candidate_name in item.institution_names),
                    default=0.0,
                )
            country_score = 1.0 if country_hint and any(country_hint in item.countries for item in member_features) else 0.0
            exact_id = 1.0 if configured_author_id and any(
                short_openalex_id(configured_author_id) == short_openalex_id(item.author_id) for item in member_features
            ) else 0.0
            exact_orcid = 1.0 if configured_orcid and any(configured_orcid == item.orcid for item in member_features) else 0.0
            work_signal = min(1.0, max((item.works_count for item in member_features), default=0) / 30.0)

            if exact_id or exact_orcid:
                score = 1.0
            else:
                score = 0.48 * name_score + 0.14 * rank_score + 0.25 * institution_score + 0.08 * country_score + 0.05 * work_signal
            rankings.append(
                {
                    "entity_id": entity["entity_id"],
                    "score": round(score, 6),
                    "name_score": round(name_score, 6),
                    "rank_score": round(rank_score, 6),
                    "institution_score": round(institution_score, 6),
                    "country_score": round(country_score, 6),
                    "exact_id": bool(exact_id),
                    "exact_orcid": bool(exact_orcid),
                }
            )

        rankings.sort(key=lambda item: (-item["score"], item["entity_id"]))
        if not rankings:
            seed_selection.append({"seed_id": seed_id, "selected_entity_id": "", "ambiguous": True, "rankings": []})
            continue
        best = rankings[0]
        second_score = rankings[1]["score"] if len(rankings) > 1 else 0.0
        ambiguous = bool(len(rankings) > 1 and (best["score"] - second_score) < ambiguity_margin)
        selected = entity_by_id[best["entity_id"]]
        selected["selected"] = True
        selected["selected_for_seeds"].append(seed_id)
        selected["selection_score"] = max(float(selected.get("selection_score") or 0.0), float(best["score"]))
        selected["selection_ambiguous"] = bool(selected.get("selection_ambiguous") or ambiguous)
        seed_selection.append(
            {
                "seed_id": seed_id,
                "selected_entity_id": best["entity_id"],
                "score": best["score"],
                "ambiguous": ambiguous,
                "rankings": rankings,
            }
        )

    return {
        "entities": sorted(entities, key=lambda item: item["entity_id"]),
        "author_to_entity": author_to_entity,
        "evidence": evidence,
        "seed_selection": seed_selection,
        "merge_threshold": merge_threshold,
        "evidence_threshold": evidence_threshold,
    }
