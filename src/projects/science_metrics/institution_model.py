"""Modelo heurístico e auditável para inferência da instituição principal.

As evidências são extraídas das afiliações presentes nas autorias dos trabalhos. O score
combina frequência, recência, persistência temporal e suporte no trabalho mais recente,
com fuzzy matching opcional para consolidar nomes institucionais semelhantes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rapidfuzz.fuzz import token_set_ratio

from projects.science_metrics.utils import normalize_name, short_openalex_id


@dataclass
class InstitutionEvidence:
    """Acumulador de evidências de afiliação usado para pontuar uma possível instituição principal."""
    key: str
    openalex_id: str
    name: str
    country: str
    work_ids: set[str]
    years: list[int]
    recency_weight: float = 0.0
    latest_year: int = 0


def find_authorship(work: dict[str, Any], author_ids: set[str]) -> dict[str, Any] | None:
    """Localiza em um trabalho a autoria correspondente a qualquer um dos identificadores de autor informados."""
    short_ids = {short_openalex_id(value) for value in author_ids}
    for authorship in work.get("authorships") or []:
        author_id = str(authorship.get("author_id") or (authorship.get("author") or {}).get("id") or "")
        if author_id in author_ids or short_openalex_id(author_id) in short_ids:
            return authorship
    return None


def infer_principal_institution(
    *,
    author_ids: set[str],
    works: list[dict[str, Any]],
    fuzzy_threshold: float = 92.0,
    recency_decay: float = 0.86,
) -> dict[str, Any]:
    """Infere a instituição principal a partir das afiliações observadas nos trabalhos e devolve ranking, confiança e evidências."""
    raw_evidence: list[dict[str, Any]] = []
    max_year = max((int(work.get("publication_year") or 0) for work in works), default=0)

    for work in works:
        authorship = find_authorship(work, author_ids)
        if not authorship:
            continue
        work_id = str(work.get("id") or "")
        year = int(work.get("publication_year") or 0)
        for institution in authorship.get("institutions") or []:
            name = str(institution.get("display_name") or institution.get("name") or "").strip()
            country = str(institution.get("country_code") or institution.get("country") or "").upper()
            openalex_id = str(institution.get("id") or institution.get("openalex_id") or "")
            if not name and not openalex_id:
                continue
            raw_evidence.append(
                {
                    "openalex_id": openalex_id,
                    "name": name or openalex_id,
                    "country": country,
                    "work_id": work_id,
                    "year": year,
                }
            )

    clusters: dict[str, InstitutionEvidence] = {}
    aliases: dict[str, str] = {}

    for evidence in raw_evidence:
        openalex_id = evidence["openalex_id"]
        normalized = normalize_name(evidence["name"])
        key = openalex_id or normalized
        if not openalex_id and normalized:
            best_key = ""
            best_score = 0.0
            for existing_key, item in clusters.items():
                if item.openalex_id:
                    continue
                score = token_set_ratio(normalized, normalize_name(item.name))
                if score > best_score:
                    best_score = score
                    best_key = existing_key
            if best_score >= fuzzy_threshold:
                key = best_key
        if key not in clusters:
            clusters[key] = InstitutionEvidence(
                key=key,
                openalex_id=openalex_id,
                name=evidence["name"],
                country=evidence["country"],
                work_ids=set(),
                years=[],
            )
        item = clusters[key]
        if openalex_id and not item.openalex_id:
            item.openalex_id = openalex_id
        if evidence["country"] and not item.country:
            item.country = evidence["country"]
        item.work_ids.add(evidence["work_id"])
        if evidence["year"]:
            item.years.append(evidence["year"])
            item.latest_year = max(item.latest_year, evidence["year"])
            age = max(0, max_year - evidence["year"])
            item.recency_weight += recency_decay ** age
        aliases[evidence["name"]] = key

    if not clusters:
        return {
            "primary": None,
            "candidates": [],
            "evidence_works": 0,
            "confidence": 0.0,
            "method": "frequency_recency_fuzzy_v1",
        }

    total_works = max(1, len({work_id for item in clusters.values() for work_id in item.work_ids}))
    total_recency = sum(item.recency_weight for item in clusters.values()) or 1.0
    all_years = {year for item in clusters.values() for year in item.years}
    total_years = max(1, len(all_years))

    candidates: list[dict[str, Any]] = []
    for item in clusters.values():
        frequency_share = len(item.work_ids) / total_works
        recency_share = item.recency_weight / total_recency
        year_share = len(set(item.years)) / total_years
        latest_support = 1.0 if item.latest_year == max_year and max_year else 0.0
        score = 0.55 * frequency_share + 0.25 * recency_share + 0.10 * year_share + 0.10 * latest_support
        candidates.append(
            {
                "key": item.key,
                "openalex_id": item.openalex_id,
                "name": item.name,
                "country": item.country,
                "works_count": len(item.work_ids),
                "work_ids": sorted(item.work_ids),
                "years": sorted(set(item.years)),
                "latest_year": item.latest_year,
                "frequency_share": round(frequency_share, 6),
                "recency_share": round(recency_share, 6),
                "year_share": round(year_share, 6),
                "score": round(score, 6),
            }
        )

    candidates.sort(key=lambda item: (-item["score"], -item["works_count"], item["name"]))
    top = candidates[0]
    second = candidates[1]["score"] if len(candidates) > 1 else 0.0
    confidence = min(1.0, max(0.0, top["score"] + max(0.0, top["score"] - second) * 0.6))
    return {
        "primary": top,
        "candidates": candidates,
        "evidence_works": total_works,
        "confidence": round(confidence, 6),
        "method": "frequency_recency_fuzzy_v1",
    }


def aggregate_local_affiliations(works: list[dict[str, Any]], author_id: str) -> list[dict[str, Any]]:
    """Extrai as autorias relevantes de uma coleção local de trabalhos para um determinado autor."""
    result: list[dict[str, Any]] = []
    for work in works:
        authorship = find_authorship(work, {author_id})
        if authorship:
            result.append(authorship)
    return result
