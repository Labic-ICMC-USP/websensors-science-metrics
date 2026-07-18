# Arquitetura resumida

## Camada bruta normalizada

- `authors`
- `institutions`
- `works`

## KG bruta

- `researcher_seeds`
- `CANDIDATE_FOR`
- `AUTHORED`
- `AFFILIATED_WITH`
- `ASSOCIATED_WITH_INSTITUTION`
- `CITES`

## KG enriquecida

### Identidade

- `researcher_entities`
- `SAME_AS_EVIDENCE`
- `RESOLVED_AS`
- `REPRESENTS_RESEARCHER`

### Instituição principal

- `principal_institutions`
- `HAS_PRIMARY_INSTITUTION`
- `DERIVED_FROM_INSTITUTION`

### Coautores

- `coauthor_entities`
- `RESOLVED_AS_COAUTHOR`

## Produtos analíticos

- `report_production`
- `report_group_summary`
- `COLLABORATES_WITH`
