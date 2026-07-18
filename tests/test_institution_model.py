from projects.science_metrics.institution_model import infer_principal_institution


def _work(work_id, year, author_id, institution_id, name, country):
    return {
        "id": work_id,
        "publication_year": year,
        "authorships": [
            {
                "author_id": author_id,
                "institutions": [
                    {"id": institution_id, "name": name, "country": country}
                ],
            }
        ],
    }


def test_institution_model_prefers_frequent_persistent_affiliation():
    author_id = "https://openalex.org/A1"
    works = [
        _work("W1", 2022, author_id, "I1", "Universidade de Sao Paulo", "BR"),
        _work("W2", 2023, author_id, "I1", "Universidade de Sao Paulo", "BR"),
        _work("W3", 2024, author_id, "I1", "Universidade de Sao Paulo", "BR"),
        _work("W4", 2025, author_id, "I2", "Visiting University", "US"),
    ]
    result = infer_principal_institution(author_ids={author_id}, works=works)
    assert result["primary"]["openalex_id"] == "I1"
    assert result["primary"]["country"] == "BR"
    assert result["confidence"] > 0
