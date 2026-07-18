from projects.science_metrics.entity_resolution import resolve_candidates
from projects.science_metrics.utils import json_dumps


def _author(author_id, name, seed_id, rank, institution=None, orcid=""):
    return {
        "openalex_id": author_id,
        "display_name": name,
        "orcid": orcid,
        "works_count": 10,
        "cited_by_count": 100,
        "candidate_seeds_json": json_dumps([{"seed_id": seed_id, "rank": rank}]),
        "last_known_institutions_json": json_dumps(institution or []),
    }


def _work(work_id, author_ids, doi="", institution_name="USP", country="BR"):
    return {
        "openalex_id": work_id,
        "doi": doi,
        "topics_json": "[]",
        "authorships_json": json_dumps(
            [
                {
                    "author_id": author_id,
                    "author_name": author_id,
                    "institutions": [
                        {"id": "https://openalex.org/I1", "name": institution_name, "country": country}
                    ],
                }
                for author_id in author_ids
            ]
        ),
    }


def test_merges_similar_profiles_with_shared_production():
    authors = [
        _author("https://openalex.org/A1", "Joao da Silva", "S1", 1),
        _author("https://openalex.org/A2", "João da Silva", "S1", 2),
    ]
    works = [
        _work("https://openalex.org/W1", ["https://openalex.org/A1", "https://openalex.org/A2"], "https://doi.org/10.1/x"),
        _work("https://openalex.org/W2", ["https://openalex.org/A1", "https://openalex.org/A2"], "https://doi.org/10.1/y"),
    ]
    result = resolve_candidates(
        authors=authors,
        works=works,
        seeds=[{"seed_id": "S1", "name": "Joao da Silva"}],
        config={"merge_threshold": 0.72, "evidence_edge_threshold": 0.55},
    )
    assert len(result["entities"]) == 1
    assert result["entities"][0]["selected"] is True


def test_does_not_merge_different_names_only_because_they_coauthor_everything():
    authors = [
        _author("https://openalex.org/A1", "Alice Souza", "S1", 1),
        _author("https://openalex.org/A2", "Bruno Pereira", "S1", 2),
    ]
    works = [
        _work("https://openalex.org/W1", ["https://openalex.org/A1", "https://openalex.org/A2"]),
        _work("https://openalex.org/W2", ["https://openalex.org/A1", "https://openalex.org/A2"]),
    ]
    result = resolve_candidates(
        authors=authors,
        works=works,
        seeds=[{"seed_id": "S1", "name": "Alice Souza"}],
        config={"merge_threshold": 0.72, "evidence_edge_threshold": 0.55},
    )
    assert len(result["entities"]) == 2


def test_selection_uses_seed_specific_rank_and_institution_hint():
    authors = [
        _author(
            "https://openalex.org/A1",
            "Carlos Lima",
            "S1",
            2,
            [{"id": "I1", "display_name": "Universidade de Sao Paulo", "country_code": "BR"}],
        ),
        _author(
            "https://openalex.org/A2",
            "Carlos Lima",
            "S1",
            1,
            [{"id": "I2", "display_name": "Universidade Federal do Parana", "country_code": "BR"}],
        ),
    ]
    result = resolve_candidates(
        authors=authors,
        works=[],
        seeds=[{"seed_id": "S1", "name": "Carlos Lima", "institution_hint": "Universidade de Sao Paulo"}],
        config={"merge_threshold": 0.95, "evidence_edge_threshold": 0.55},
    )
    selected_id = result["seed_selection"][0]["selected_entity_id"]
    selected = next(item for item in result["entities"] if item["entity_id"] == selected_id)
    assert "https://openalex.org/A1" in selected["raw_author_ids"]
