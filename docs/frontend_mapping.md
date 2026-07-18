# Mapeamento do frontend v11 para o pipeline

O pacote foi estruturado a partir do comportamento observado no frontend `websensors-science-metrics-v11`, mas separa coleta, resolução de identidade, enriquecimento e relatório em etapas reexecutáveis do WebSensors Flow.

| Comportamento observado no frontend | Implementação no pipeline |
|---|---|
| Busca de candidatos de autor por nome | `01_ingest_data`, com `top_n_candidates` configurável |
| Coleta paginada da produção por autor | `OpenAlexClient.fetch_works_for_author` com cursor |
| Uso de afiliações, instituições e metadados ricos dos trabalhos | Normalização em `authors`, `institutions` e `works`, preservando também o JSON bruto |
| Métricas de fonte, FWCI, acesso aberto e tópicos | Campos normalizados em `works` e documentos de `report_production` |
| Reconsulta das produções próprias dos coautores | `05_enrich_coauthors`, usando `coauthor_recent_works` |
| Produções extras dos coautores usadas apenas para classificação | Trabalhos de enriquecimento não são inseridos como produção intelectual do grupo |
| Regra de internacionalização baseada no país principal dos autores | `06_reporting`, após resolução das instituições e países principais |
| Grafo de coautoria | Arestas canônicas `COLLABORATES_WITH` entre entidades resolvidas |

## Diferença conceitual principal

O frontend trabalha diretamente com resultados consolidados para visualização. O pipeline mantém duas camadas separadas:

1. **Evidência bruta**, formada pelos registros do OpenAlex e pelo grafo inicial.
2. **Camada canônica**, formada por entidades resolvidas, instituições principais, coautores enriquecidos e relatórios.

Essa separação permite auditar por que perfis foram unidos, refazer apenas um modelo e preservar os dados originais para comparação futura.
