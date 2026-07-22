# Clarivate Research Metrics

Pipeline em Python para coletar, integrar e agregar métricas de pesquisadores e de suas produções científicas usando APIs da Clarivate.

O script principal é:

```text
clarivate_research_metrics.py
```

e expõe uma única classe pública:

```python
ClarivateResearchMetrics
```

A classe foi projetada para receber uma lista de pesquisadores identificados por **nome e ORCID**, recuperar suas produções em um período definido, enriquecer cada publicação com métricas bibliométricas e indicadores de internacionalização e gerar dois arquivos Parquet:

1. **`researchers_metrics.parquet`** — uma linha por pesquisador, com métricas agregadas;
2. **`researcher_publications_metrics.parquet`** — uma linha por pesquisador × publicação, contendo os dados usados na agregação.

---

## Visão geral

O pipeline combina três APIs:

| API | Função no pipeline |
|---|---|
| **Web of Science API Expanded** | Busca das produções por ORCID e recuperação de metadados completos, autores, identificadores, endereços, países, organizações, categorias, citações e afiliações |
| **Web of Science Researcher API** | Recuperação opcional do perfil do pesquisador e de métricas básicas associadas ao ResearcherID |
| **InCites Document Level Metrics API** | Enriquecimento das publicações com métricas normalizadas de impacto, colaboração, acesso aberto e diferentes esquemas de classificação |

O fluxo geral é:

```text
JSON de pesquisadores
        │
        │ nome + ORCID
        ▼
Web of Science API Expanded
        │
        ├── produções no período
        ├── autores
        ├── ResearcherID
        ├── afiliações
        ├── países
        ├── organizações
        ├── citações
        └── WOS UID / UT
        │
        ├──────────────────────────► Web of Science Researcher API
        │                                  │
        │                                  └── perfil e métricas básicas
        │
        ▼
InCites Document Level Metrics API
        │
        ├── CNCI
        ├── JNCI
        ├── percentis
        ├── indicadores de colaboração
        ├── Open Access
        ├── Highly Cited / Hot Paper
        └── classificações temáticas
        │
        ▼
Agregação por pesquisador
        │
        ├── impacto
        ├── internacionalização
        ├── diversidade de parceiros
        ├── mobilidade
        ├── produção por período
        └── taxonomias
        │
        ├── researchers_metrics.parquet
        └── researcher_publications_metrics.parquet
```

---

# 1. Instalação

O script requer Python 3 e as bibliotecas:

```bash
pip install requests pandas numpy pyarrow
```

Não é necessário instalar um pacote Python específico da Clarivate. As APIs são acessadas diretamente via HTTP usando `requests`.

Estrutura mínima recomendada:

```text
projeto/
├── clarivate_research_metrics.py
├── pesquisadores.json
└── executar.py
```

---

# 2. Formato da entrada

A entrada pode ser o caminho para um arquivo JSON, uma lista Python ou um dicionário Python.

## Formato recomendado

```json
[
  {
    "name": "Nome do Pesquisador",
    "orcid": "0000-0000-0000-0000"
  },
  {
    "name": "Outro Pesquisador",
    "orcid": "0000-0000-0000-000X"
  }
]
```

Também é possível usar:

```json
{
  "researchers": [
    {
      "name": "Nome do Pesquisador",
      "orcid": "0000-0000-0000-0000"
    }
  ]
}
```

Os nomes das chaves podem estar em português:

```json
{
  "pesquisadores": [
    {
      "nome": "Nome do Pesquisador",
      "orcid": "0000-0000-0000-0000"
    }
  ]
}
```

O ORCID também pode ser informado como URL:

```json
{
  "name": "Nome do Pesquisador",
  "orcid": "https://orcid.org/0000-0000-0000-0000"
}
```

A classe normaliza automaticamente o valor para:

```text
0000-0000-0000-0000
```

## Campos adicionais

Campos extras são aceitos:

```json
[
  {
    "name": "Nome do Pesquisador",
    "orcid": "0000-0000-0000-0000",
    "institution": "Universidade de São Paulo",
    "group": "LABIC",
    "internal_id": 123
  }
]
```

No Parquet agregado, esses campos são preservados com o prefixo `input_`:

```text
input_institution
input_group
input_internal_id
```

Isso permite integrar a saída do pipeline com cadastros institucionais.

---

# 3. Uso básico

```python
from clarivate_research_metrics import ClarivateResearchMetrics

pipeline = ClarivateResearchMetrics(
    wos_api_key="SUA_CHAVE_WOS_EXPANDED",
    incites_api_key="SUA_CHAVE_INCITES",
    researcher_api_key="SUA_CHAVE_RESEARCHER_API",
    verbose=True,
)

outputs = pipeline.run(
    input_json="pesquisadores.json",
    start_year=2020,
    end_year=2026,
    output_dir="./output",
)

print(outputs)
```

Resultado:

```python
{
    "researchers_parquet": "output/researchers_metrics.parquet",
    "publications_parquet": "output/researcher_publications_metrics.parquet"
}
```

---

# 4. Uso com uma lista Python

Não é obrigatório criar um arquivo JSON.

```python
from clarivate_research_metrics import ClarivateResearchMetrics

researchers = [
    {
        "name": "Pesquisador A",
        "orcid": "0000-0000-0000-0000",
    },
    {
        "name": "Pesquisador B",
        "orcid": "0000-0000-0000-000X",
    },
]

pipeline = ClarivateResearchMetrics(
    wos_api_key="SUA_CHAVE_WOS",
    incites_api_key="SUA_CHAVE_INCITES",
    researcher_api_key="SUA_CHAVE_RESEARCHER",
)

outputs = pipeline.run(
    input_json=researchers,
    start_year=2021,
    end_year=2026,
    output_dir="dados_clarivate",
)
```

---

# 5. Parâmetros da classe

A classe é inicializada da seguinte forma:

```python
ClarivateResearchMetrics(
    wos_api_key,
    incites_api_key,
    researcher_api_key=None,
    *,
    wos_base_url="https://wos-api.clarivate.com/api/wos",
    researcher_base_url="https://api.clarivate.com/apis/wos-researcher",
    incites_base_url="https://incites-api.clarivate.com/api/incites",
    incites_schemas=None,
    include_researcher_profile=True,
    include_citation_report=True,
    include_raw_profile_json=True,
    include_raw_wos_json=False,
    incites_esci=True,
    request_timeout=90,
    max_retries=6,
    verbose=True,
)
```

## Parâmetros principais

| Parâmetro | Descrição |
|---|---|
| `wos_api_key` | Chave da Web of Science API Expanded |
| `incites_api_key` | Chave da InCites Document Level Metrics API |
| `researcher_api_key` | Chave da Web of Science Researcher API |
| `incites_schemas` | Lista de esquemas de classificação a consultar |
| `include_researcher_profile` | Ativa/desativa a consulta do perfil na Researcher API |
| `include_citation_report` | Ativa/desativa a coleta do Citation Report |
| `include_raw_profile_json` | Preserva o JSON bruto do perfil no Parquet agregado |
| `include_raw_wos_json` | Preserva o registro bruto da WoS em cada publicação |
| `incites_esci` | Inclui documentos ESCI nas consultas InCites |
| `request_timeout` | Timeout HTTP em segundos |
| `max_retries` | Número máximo de tentativas para falhas temporárias |
| `verbose` | Exibe o progresso no terminal |

### Observação sobre `researcher_api_key`

Quando `researcher_api_key` não é informado, o script usa:

```python
researcher_api_key = wos_api_key
```

Isso é apenas uma conveniência. Dependendo das licenças e credenciais atribuídas à aplicação no Developer Portal, a Researcher API pode exigir uma chave com permissão específica. Nesse caso, informe explicitamente a chave correspondente.

---

# 6. Parâmetros do método `run()`

```python
outputs = pipeline.run(
    input_json="pesquisadores.json",
    start_year=2020,
    end_year=2026,
    output_dir="./output",
    researchers_filename="researchers_metrics.parquet",
    publications_filename="researcher_publications_metrics.parquet",
)
```

| Parâmetro | Descrição |
|---|---|
| `input_json` | Arquivo JSON, lista Python ou dicionário Python |
| `start_year` | Primeiro ano do período |
| `end_year` | Último ano do período |
| `output_dir` | Diretório onde os Parquets serão gravados |
| `researchers_filename` | Nome do arquivo agregado |
| `publications_filename` | Nome do arquivo publicação × pesquisador |

O período é inclusivo.

Exemplo:

```python
start_year=2020
end_year=2026
```

busca as produções de 2020 até 2026.

---

# 7. Como o pesquisador é localizado

O identificador inicial obrigatório é o **ORCID**.

Para cada pesquisador, o script executa uma busca na Web of Science equivalente a:

```text
AI=("0000-0000-0000-0000") AND PY=(2020-2026)
```

A partir dos registros encontrados, o pipeline:

1. identifica o autor associado ao ORCID;
2. coleta os `ResearcherID` encontrados nos registros;
3. seleciona o ResearcherID mais frequente;
4. calcula uma medida simples de confiança:

```text
frequência do ResearcherID mais frequente
------------------------------------------
total de ocorrências de ResearcherIDs
```

Se nenhum ResearcherID for encontrado nas produções do período, o script realiza uma busca adicional usando o ORCID sem restrição temporal.

As seguintes colunas são preservadas no resultado agregado:

```text
researcher_id_wos
researcher_id_candidates_json
researcher_id_resolution_confidence
matched_author_names_json
```

Essa estratégia também torna o processo auditável quando diferentes ResearcherIDs aparecem associados ao mesmo ORCID nos registros recuperados.

---

# 8. Coleta das produções

A Web of Science API Expanded é usada como fonte principal para as publicações.

Para cada registro, o script tenta recuperar:

## Identificação

```text
wos_uid
incites_ut
doi
issn
eissn
pmid
```

## Dados bibliográficos

```text
title
source_title
publication_year
publication_date
early_access_year
publication_type
document_types_json
```

## Autores

```text
author_count
coauthor_count
authors_json
author_orcids_json
author_rids_json
```

## Citações

```text
wos_times_cited
all_databases_times_cited
```

## Afiliações e internacionalização

```text
countries_json
country_count
is_international_wos

organizations_json
organization_count
addresses_json

researcher_affiliation_countries_json
researcher_affiliations_json
researcher_addresses_json
```

## Conteúdo e classificação

```text
wos_categories_json
wos_native_citation_topics_json
wos_native_sdg_json
keywords_json
abstract
```

Quando:

```python
include_raw_wos_json=True
```

também é criada a coluna:

```text
wos_raw_json
```

---

# 9. Deduplicação de publicações

Dentro de cada pesquisador, registros duplicados são removidos pelo `WOS UID`.

Quando a mesma publicação pertence a dois ou mais pesquisadores da lista de entrada:

- ela aparece uma vez para cada pesquisador no Parquet `pesquisador × publicação`;
- a chamada ao InCites é feita apenas uma vez para aquele UT.

Isso reduz chamadas desnecessárias sem perder a relação individual entre cada pesquisador e cada produção.

---

# 10. Web of Science Researcher API

Quando um `ResearcherID` é resolvido e:

```python
include_researcher_profile=True
```

o script consulta a Researcher API.

Os campos normalizados procurados pelo parser são:

```text
profile_h_index
profile_times_cited
profile_document_count
profile_claim_status
profile_primary_organization
profile_primary_country
```

Como a estrutura de resposta pode evoluir, o parser procura aliases comuns dos campos.

Por padrão, o JSON completo retornado pela API também é preservado:

```text
profile_raw_json
```

Para desativar:

```python
pipeline = ClarivateResearchMetrics(
    ...,
    include_raw_profile_json=False,
)
```

Também é possível desativar completamente a consulta de perfil:

```python
pipeline = ClarivateResearchMetrics(
    ...,
    include_researcher_profile=False,
)
```

---

# 11. Citation Report

Por padrão:

```python
include_citation_report=True
```

O pipeline solicita o Citation Report para:

1. o conjunto completo retornado pela busca do pesquisador;
2. o recorte temporal definido por `start_year` e `end_year`.

Os campos disponíveis na resposta são convertidos em colunas como:

```text
citation_report_all_<nivel>_times_cited
citation_report_all_<nivel>_times_cited_sans_self
citation_report_all_<nivel>_average_per_item
citation_report_all_<nivel>_average_per_year
citation_report_all_<nivel>_citing_items_sans_self
citation_report_all_<nivel>_h_index
citation_report_all_<nivel>_citing_years_json
```

e:

```text
citation_report_window_<nivel>_...
```

O código ignora o Citation Report quando o conjunto alcança 10.000 registros ou mais.

---

# 12. Métricas InCites por publicação

A consulta do InCites é realizada a partir do UT derivado do `WOS UID`.

Exemplo:

```text
WOS:000123456789001
```

é convertido em:

```text
000123456789001
```

O script consulta os documentos em lotes de até 100 UTs.

Entre os principais campos coletados estão:

## Impacto

```text
incites_times_cited
incites_journal_expected_citations
incites_jnci
incites_impact_factor
incites_harmonic_mean_category_expected_citations
incites_avg_cnci
```

## Excelência

```text
incites_esi_highly_cited_paper
incites_esi_hot_paper
```

## Colaboração

```text
incites_is_international_collab
incites_is_institution_collab
incites_is_industry_collab
```

## Acesso aberto

```text
incites_open_access_flag
incites_open_access_status_json
```

## Cobertura

```text
incites_available
```

Esse campo permite medir quantas publicações efetivamente receberam métricas do InCites.

---

# 13. Esquemas de classificação do InCites

Por padrão, o script consulta:

```python
DEFAULT_INCITES_SCHEMAS = (
    "wos",
    "sdg",
    "ct",
    "esi",
    "fapesp",
    "capesl1",
    "capesl2",
    "capesl3",
    "oecd",
)
```

Interpretação:

| Código | Classificação |
|---|---|
| `wos` | Web of Science Categories |
| `sdg` | UN Sustainable Development Goals |
| `ct` | Citation Topics |
| `esi` | Essential Science Indicators |
| `fapesp` | Classificação FAPESP |
| `capesl1` | CAPES nível 1 |
| `capesl2` | CAPES nível 2 |
| `capesl3` | CAPES nível 3 |
| `oecd` | OECD |

Para cada esquema, o script gera campos semelhantes a:

```text
incites_<schema>_subjects_json
incites_<schema>_codes_json
incites_<schema>_details_json
incites_<schema>_best_subject
incites_<schema>_best_code
incites_<schema>_best_cat_percentile
incites_<schema>_best_cnci
incites_<schema>_max_cat_percentile
```

Exemplo para SDGs:

```text
incites_sdg_subjects_json
incites_sdg_codes_json
incites_sdg_details_json
incites_sdg_best_subject
incites_sdg_best_code
incites_sdg_best_cat_percentile
incites_sdg_best_cnci
incites_sdg_max_cat_percentile
```

O campo `details_json` preserva a estrutura completa recebida para evitar perda de informação.

## Selecionando somente alguns esquemas

```python
pipeline = ClarivateResearchMetrics(
    wos_api_key="...",
    incites_api_key="...",
    researcher_api_key="...",
    incites_schemas=[
        "wos",
        "sdg",
        "ct",
    ],
)
```

Isso reduz o número de chamadas ao InCites.

---

# 14. Internacionalização

A internacionalização é analisada usando duas fontes independentes.

## 14.1. Indicador InCites

```text
incites_is_international_collab
```

É o indicador de colaboração internacional fornecido diretamente pelo InCites.

## 14.2. Inferência a partir das afiliações WoS

O script também examina os países presentes nos endereços dos autores.

Uma publicação é marcada como internacional pela WoS quando:

```text
número de países distintos >= 2
```

Coluna:

```text
is_international_wos
```

Isso permite comparar a classificação calculada a partir dos registros com o indicador entregue pelo InCites.

---

# 15. País-base e parceiros internacionais

Para cada pesquisador, o script coleta os países associados às suas próprias afiliações nas publicações.

O país-base é inferido como o país mais frequente no período:

```text
home_country_inferred
```

Em seguida, para cada publicação, são calculados:

```text
foreign_partner_countries_json
foreign_partner_country_count
has_foreign_partner_inferred
```

No agregado por pesquisador:

```text
unique_countries_count
countries_frequency_json

unique_foreign_partner_countries_count
foreign_partner_countries_frequency_json

researcher_affiliation_country_count_period
researcher_affiliation_countries_frequency_json

unique_organizations_count
organizations_frequency_json
```

---

# 16. Diversidade geográfica das colaborações

O pipeline calcula a entropia de Shannon sobre a frequência dos países parceiros estrangeiros:

```text
partner_country_diversity_shannon
```

Quanto mais concentradas as colaborações em poucos países, menor tende a ser o valor.

Quanto mais distribuídas as colaborações entre diferentes países, maior tende a ser o valor.

Essa métrica complementa a simples contagem:

```text
unique_foreign_partner_countries_count
```

pois dois pesquisadores podem colaborar com o mesmo número de países, mas apresentar distribuições muito diferentes de suas parcerias.

---

# 17. Mobilidade internacional

O pipeline produz dois tipos de indicador.

## Por publicação

```text
researcher_is_internationally_mobile_in_record
```

Valor `1` quando o pesquisador aparece associado a pelo menos dois países de afiliação naquele registro.

## No período

```text
researcher_mobility_flag_period
```

Valor `1` quando foram observados pelo menos dois países diferentes associados às afiliações do pesquisador ao longo do período.

Esses indicadores devem ser interpretados como **sinais bibliométricos de mobilidade ou múltipla afiliação**, e não como uma reconstrução definitiva da trajetória profissional do pesquisador.

---

# 18. Comparação entre impacto internacional e doméstico

O Parquet agregado compara as publicações classificadas pelo InCites como internacionais e domésticas.

São calculadas métricas como:

```text
international_cnci_mean
domestic_cnci_mean

international_vs_domestic_cnci_ratio
international_minus_domestic_cnci

international_citations_mean
domestic_citations_mean

international_vs_domestic_citations_ratio
```

Exemplo de interpretação:

```text
international_vs_domestic_cnci_ratio > 1
```

indica que, no período analisado, o CNCI médio das publicações com colaboração internacional foi superior ao CNCI médio das publicações classificadas como domésticas.

É importante considerar o número de publicações em cada grupo antes de interpretar essas razões.

---

# 19. Arquivo `researchers_metrics.parquet`

Granularidade:

```text
1 linha = 1 pesquisador
```

O arquivo agrega as publicações do período e combina informações de perfil, impacto e internacionalização.

## Identificação

```text
researcher_name
researcher_orcid
researcher_id_wos
researcher_id_candidates_json
researcher_id_resolution_confidence
matched_author_names_json
```

## Período e cobertura

```text
period_start_year
period_end_year
wos_records_found
publication_count

incites_publication_count
incites_coverage_rate
```

## Perfil

```text
profile_h_index
profile_times_cited
profile_document_count
profile_claim_status
profile_primary_organization
profile_primary_country
profile_raw_json
```

## Estatísticas de impacto

Para várias métricas são produzidos:

```text
_count
_sum
_mean
_median
_min
_max
_std
```

Exemplos:

```text
wos_times_cited_mean
incites_times_cited_mean
cnci_mean
cnci_median
jnci_mean
journal_impact_factor_mean
wos_category_percentile_mean
```

## H-index calculado no período

```text
period_h_index_computed
```

Esse valor é calculado exclusivamente a partir das publicações recuperadas no intervalo informado.

Ele não deve ser confundido com:

```text
profile_h_index
```

que representa o valor obtido do perfil da Researcher API.

---

# 20. Publicações de maior impacto

O agregado contém contagens e proporções de publicações em faixas de percentil:

```text
top_1pct_publication_count
top_1pct_publication_rate

top_10pct_publication_count
top_10pct_publication_rate

top_25pct_publication_count
top_25pct_publication_rate
```

Também são agregados:

```text
esi_highly_cited_paper_count
esi_highly_cited_paper_rate

esi_hot_paper_count
esi_hot_paper_rate
```

---

# 21. Indicadores agregados de colaboração

São geradas contagens e proporções para:

```text
international_collaboration_incites_count
international_collaboration_incites_rate

international_collaboration_wos_count
international_collaboration_wos_rate

institutional_collaboration_count
institutional_collaboration_rate

industry_collaboration_count
industry_collaboration_rate

foreign_partner_inferred_count
foreign_partner_inferred_rate

open_access_count
open_access_rate
```

---

# 22. Produção temporal e veículos

O arquivo agregado inclui:

```text
publications_by_year_json
document_types_frequency_json
source_titles_frequency_json
unique_source_titles_count
```

Exemplo:

```json
{
  "2022": 8,
  "2023": 12,
  "2024": 15
}
```

---

# 23. Taxonomias agregadas

Para cada esquema InCites, o script agrega as áreas encontradas nas publicações.

Exemplo:

```text
sdg_unique_subject_count
sdg_subject_frequency_json

ct_unique_subject_count
ct_subject_frequency_json

wos_unique_subject_count
wos_subject_frequency_json
```

O mesmo padrão é aplicado aos demais esquemas selecionados.

---

# 24. Arquivo `researcher_publications_metrics.parquet`

Granularidade:

```text
1 linha = 1 pesquisador × 1 publicação
```

Esse arquivo funciona como a camada analítica detalhada e como a origem das métricas agregadas.

Uma mesma publicação pode aparecer em múltiplas linhas quando diferentes pesquisadores da entrada forem coautores do mesmo trabalho.

Entre os principais grupos de campos estão:

## Pesquisador

```text
researcher_name
researcher_orcid
researcher_id_wos
matched_author_name
matched_author_name_similarity
```

## Publicação

```text
wos_uid
incites_ut
title
source_title
publication_year
publication_date
publication_type
doi
issn
eissn
pmid
```

## Autoria

```text
author_count
coauthor_count
authors_json
author_orcids_json
author_rids_json
```

## Afiliações

```text
countries_json
organizations_json
addresses_json

researcher_affiliation_countries_json
researcher_affiliations_json
researcher_addresses_json
```

## Internacionalização

```text
country_count
is_international_wos

home_country_inferred
foreign_partner_countries_json
foreign_partner_country_count
has_foreign_partner_inferred

researcher_is_internationally_mobile_in_record

incites_is_international_collab
incites_is_institution_collab
incites_is_industry_collab
```

## Impacto

```text
wos_times_cited
all_databases_times_cited

incites_times_cited
incites_avg_cnci
incites_jnci
incites_impact_factor
incites_journal_expected_citations
```

## Classificações

```text
wos_categories_json
wos_native_citation_topics_json
wos_native_sdg_json

incites_wos_...
incites_sdg_...
incites_ct_...
incites_esi_...
incites_fapesp_...
incites_capesl1_...
incites_capesl2_...
incites_capesl3_...
incites_oecd_...
```

---

# 25. Lendo os Parquets

## Pandas

```python
import pandas as pd

researchers = pd.read_parquet(
    "output/researchers_metrics.parquet"
)

publications = pd.read_parquet(
    "output/researcher_publications_metrics.parquet"
)

print(researchers.head())
print(publications.head())
```

## Exemplo: ranking por CNCI médio

```python
ranking = (
    researchers[
        [
            "researcher_name",
            "publication_count",
            "cnci_mean",
            "international_collaboration_incites_rate",
        ]
    ]
    .sort_values(
        "cnci_mean",
        ascending=False,
    )
)

print(ranking)
```

## Exemplo: pesquisadores com maior internacionalização

```python
ranking = (
    researchers[
        [
            "researcher_name",
            "international_collaboration_incites_rate",
            "unique_foreign_partner_countries_count",
            "partner_country_diversity_shannon",
        ]
    ]
    .sort_values(
        "international_collaboration_incites_rate",
        ascending=False,
    )
)

print(ranking)
```

## Exemplo: impacto internacional versus doméstico

```python
comparison = researchers[
    [
        "researcher_name",
        "international_cnci_mean",
        "domestic_cnci_mean",
        "international_vs_domestic_cnci_ratio",
    ]
]

print(comparison)
```

## Exemplo: colaboração por país

```python
import json

row = researchers.iloc[0]

countries = json.loads(
    row["foreign_partner_countries_frequency_json"]
)

print(countries)
```

## Exemplo: publicações associadas a SDGs

```python
sdg_publications = publications[
    publications["incites_sdg_subjects_json"] != "[]"
]

print(
    sdg_publications[
        [
            "researcher_name",
            "title",
            "publication_year",
            "incites_sdg_subjects_json",
            "incites_avg_cnci",
        ]
    ]
)
```

---

# 26. Tratamento de falhas e limites

O cliente HTTP implementa:

- timeout configurável;
- repetição automática de chamadas;
- backoff exponencial;
- tratamento de HTTP `429`;
- nova tentativa para erros `500`, `502`, `503` e `504`;
- suporte ao cabeçalho `Retry-After`;
- mensagens explícitas para erros `401` e `403`;
- throttling independente por serviço.

Os intervalos internos padrão são:

```python
{
    "wos": 0.40,
    "researcher": 0.23,
    "incites": 0.56,
}
```

Esses valores foram definidos para manter alguma folga operacional, mas os limites efetivos dependem do plano contratado e das políticas vigentes da Clarivate.

---

# 27. Controle do volume de chamadas

O maior volume de chamadas pode vir do InCites porque cada esquema de classificação é consultado separadamente.

Com os nove esquemas padrão:

```text
wos
sdg
ct
esi
fapesp
capesl1
capesl2
capesl3
oecd
```

o custo aproximado em chamadas ao InCites é:

```text
número de esquemas
×
ceil(número de UTs únicos / 100)
```

Por exemplo, para 1.000 publicações únicas:

```text
9 × ceil(1000 / 100)
= 9 × 10
= 90 chamadas
```

Caso apenas internacionalização e impacto sejam necessários, é possível reduzir os esquemas:

```python
pipeline = ClarivateResearchMetrics(
    wos_api_key="...",
    incites_api_key="...",
    researcher_api_key="...",
    incites_schemas=["wos"],
)
```

Ou, para impacto e análise temática:

```python
incites_schemas=[
    "wos",
    "sdg",
    "ct",
]
```

---

# 28. Onde conseguir as APIs

> Situação verificada na documentação oficial da Clarivate em julho de 2026. Licenciamento, limites e condições contratuais podem mudar. Para uso institucional, confirme sempre as condições aplicáveis à sua organização no Clarivate Developer Portal e com a biblioteca ou unidade responsável pela assinatura institucional.

O ponto de entrada é o:

**Clarivate Developer Portal**

```text
https://developer.clarivate.com/
```

O fluxo informado pela Clarivate é:

1. criar ou acessar uma conta no Developer Portal;
2. registrar uma aplicação;
3. localizar a API desejada;
4. solicitar a assinatura do plano correspondente;
5. aguardar a aprovação quando necessária;
6. usar a API Key vinculada à aplicação.

A Clarivate recomenda o uso de e-mail institucional para solicitações de acesso.

Página oficial com perguntas frequentes:

```text
https://developer.clarivate.com/content/developer-portal-faq
```

---

# 29. O que é público, gratuito e pago

É importante diferenciar:

- acesso público à **documentação**;
- criação gratuita de conta no **Developer Portal**;
- existência de um **plano gratuito de API**;
- acesso aos produtos Web of Science/InCites;
- licença específica para uma API.

Ter acesso ao site do Web of Science ou conseguir visualizar um perfil de pesquisador não significa automaticamente que a API correspondente esteja liberada.

## Resumo

| Recurso | Situação geral | Usado diretamente por este script? |
|---|---|---:|
| Clarivate Developer Portal | Acesso/registro público | Sim, para solicitar credenciais |
| Documentação das APIs | Pública | Sim, como referência |
| Web of Science Starter API — Free Trial | Gratuita, com limitações | Não |
| Web of Science Starter API — planos institucionais gratuitos elegíveis | Dependem de assinatura institucional | Não |
| Web of Science API Expanded | Licença paga | **Sim** |
| Web of Science Researcher API | Licença paga adicional | **Sim, opcionalmente** |
| InCites Document Level Metrics API | Licença paga | **Sim** |
| ORCID informado na entrada | Identificador aberto fornecido pelo usuário | Sim |

---

# 30. Web of Science Starter API: opção gratuita, mas não usada pelo script

Página oficial:

```text
https://developer.clarivate.com/apis/wos-starter
```

A documentação oficial informa diferentes planos.

## Free Trial Plan

Disponível mesmo para quem não pertence a uma instituição assinante do Web of Science.

Na documentação consultada em julho de 2026:

```text
50 requisições por dia
```

e o plano gratuito de avaliação não retorna `times cited`.

Esse plano pode ser útil para:

- testes de integração;
- resolução de DOI;
- recuperação de metadados bibliográficos básicos;
- protótipos de pequeno volume.

Entretanto, ele **não substitui a Web of Science API Expanded para o funcionamento atual deste pipeline**, porque o script depende de metadados detalhados, especialmente endereços e afiliações, para as análises de internacionalização.

## Free Institutional Member Plan

A documentação informa um plano gratuito para membros de instituições assinantes do Web of Science, com acesso a contagens de citações e limite publicado de até:

```text
5.000 requisições por dia
```

## Free Institutional Integration Plan

A documentação também descreve um plano institucional de integração com limite publicado de até:

```text
20.000 requisições por dia
```

A elegibilidade depende da situação institucional e deve ser confirmada no Developer Portal.

---

# 31. Web of Science API Expanded

Página oficial:

```text
https://developer.clarivate.com/apis/wos
```

A API Expanded é a principal dependência bibliográfica deste script.

Segundo a documentação oficial consultada, o acesso:

```text
requer licença paga
```

A disponibilidade e o plano dependem da assinatura institucional.

Os planos publicados pela Clarivate incluem limites anuais de Full Records:

| Plano | Requisições por segundo | Full Records por ano |
|---|---:|---:|
| Basic | 2 | 50.000 |
| Intermediate | 2 | 250.000 |
| Advanced | 3 | 1.000.000 |
| Premium | 5 | 3.000.000 |

Os limites efetivamente atribuídos devem ser verificados no contrato da instituição.

## Por que o script usa a Expanded?

Principalmente porque ela fornece metadados completos necessários para análises como:

```text
pesquisador
   │
   ├── publicação
   │      ├── autores
   │      ├── endereços
   │      ├── instituições
   │      └── países
   │
   └── internacionalização
```

Sem os endereços e vínculos completos, a reconstrução detalhada da colaboração internacional fica limitada.

---

# 32. Web of Science Researcher API

Página oficial:

```text
https://developer.clarivate.com/apis/wos-researcher
```

A documentação oficial informa que essa API:

```text
requer uma licença paga adicional a uma assinatura Web of Science
```

O plano publicado possui:

```text
até 5 requisições por segundo
até 5.000 requisições por dia
```

Essa API é usada pelo script para complementar os dados do pesquisador com informações como:

```text
h-index
times cited
document count
claim status
afiliação principal
país
```

## A Researcher API é obrigatória?

Para o pipeline completo conforme configurado por padrão, ela é utilizada.

Contudo, é possível executar a coleta sem consultar os perfis:

```python
pipeline = ClarivateResearchMetrics(
    wos_api_key="...",
    incites_api_key="...",
    include_researcher_profile=False,
)
```

Nesse caso, as métricas de perfil ficarão ausentes, mas a coleta das publicações e as agregações construídas a partir delas continuam sendo realizadas.

---

# 33. InCites Document Level Metrics API

Página oficial:

```text
https://developer.clarivate.com/apis/incites
```

A documentação oficial informa que o acesso:

```text
requer licença paga
```

O plano padrão publicado em julho de 2026 informa:

```text
2.000 requisições por dia
2 requisições por segundo
```

A FAQ do Developer Portal também informa que solicitações de acesso à API InCites passam por avaliação do caso de uso e orienta consultar a biblioteca da instituição para informações de preço e licenciamento.

Essa API é essencial para as métricas normalizadas usadas neste pipeline:

```text
CNCI
JNCI
percentis
expected citations
colaboração internacional
colaboração institucional
colaboração com indústria
Open Access
Highly Cited Paper
Hot Paper
SDGs
Citation Topics
demais esquemas de classificação
```

---

# 34. Qual combinação de licenças é necessária?

Para executar o script **com todos os recursos ativados**, é necessário ter credenciais válidas para:

```text
Web of Science API Expanded
+
Web of Science Researcher API
+
InCites Document Level Metrics API
```

Na prática, o acesso é determinado pelo contrato da instituição.

A FAQ da Clarivate informa que o acesso às APIs acadêmicas pode depender das assinaturas Web of Science e InCites e que eventuais custos adicionais devem ser verificados com a biblioteca institucional.

Portanto, antes de solicitar uma compra individual, é recomendável verificar se a universidade ou instituição já possui:

```text
Web of Science
InCites Benchmarking & Analytics
licenças de API associadas
```

Em instituições grandes, essas licenças podem ser administradas centralmente pela biblioteca.

---

# 35. Cenários de execução conforme as APIs disponíveis

## Cenário A — todas as APIs disponíveis

```text
Expanded + Researcher + InCites
```

Resultado:

- produções completas;
- afiliações e países;
- perfil do pesquisador;
- métricas normalizadas;
- internacionalização;
- SDGs e outras taxonomias.

É o cenário recomendado.

---

## Cenário B — Expanded + InCites

Configuração:

```python
pipeline = ClarivateResearchMetrics(
    wos_api_key="...",
    incites_api_key="...",
    include_researcher_profile=False,
)
```

Resultado:

- produções completas;
- afiliações e países;
- internacionalização detalhada;
- métricas InCites;
- ausência das métricas diretas do perfil da Researcher API.

Este cenário continua bastante completo para análise bibliométrica por período.

---

## Cenário C — somente Starter API

O script atual **não funciona diretamente com a Starter API**.

Seria necessário implementar uma versão alternativa do coletor WoS.

Além disso, a disponibilidade de metadados de afiliação é mais limitada, o que reduziria a capacidade de reconstruir a internacionalização detalhada.

---

## Cenário D — sem InCites

O script atual exige `incites_api_key` no construtor e sempre executa a etapa de enriquecimento InCites.

Uma versão futura poderia tornar o InCites opcional, permitindo executar apenas:

```text
WoS Expanded
+
métricas bibliográficas locais
+
internacionalização baseada em afiliações
```

Entretanto, seriam perdidos indicadores como CNCI e várias classificações normalizadas.

---

# 36. Como solicitar as credenciais

## Passo 1 — acessar o Developer Portal

```text
https://developer.clarivate.com/
```

## Passo 2 — criar uma aplicação

Depois do login, registre a aplicação que utilizará as APIs.

Use uma descrição clara, por exemplo:

```text
Institutional research analytics pipeline for bibliometric indicators,
international collaboration analysis and scientific impact assessment.
```

## Passo 3 — solicitar as APIs

Solicite, conforme a necessidade:

```text
Web of Science API Expanded
Web of Science Researcher API
InCites Document Level Metrics API
```

## Passo 4 — verificar a assinatura institucional

Antes ou durante a solicitação, confirme com a biblioteca:

- se a instituição possui Web of Science;
- se possui InCites;
- se há direito contratual a APIs;
- quais limites foram contratados;
- se é necessária licença adicional.

## Passo 5 — configurar as chaves no código

Exemplo:

```python
pipeline = ClarivateResearchMetrics(
    wos_api_key="CHAVE_EXPANDED",
    incites_api_key="CHAVE_INCITES",
    researcher_api_key="CHAVE_RESEARCHER",
)
```

O script envia a chave usando o cabeçalho:

```text
X-ApiKey
```

---

# 37. Segurança das chaves

O script aceita as chaves diretamente como parâmetros porque isso simplifica o uso em ambientes controlados.

Exemplo:

```python
pipeline = ClarivateResearchMetrics(
    wos_api_key="...",
    incites_api_key="...",
    researcher_api_key="...",
)
```

Evite publicar arquivos contendo credenciais em:

- repositórios Git públicos;
- notebooks compartilhados;
- logs;
- arquivos de exemplo;
- documentação pública.

Para ambientes menos controlados, as chaves podem ser lidas externamente e passadas para a classe sem modificar o script:

```python
from pathlib import Path

wos_key = Path("/local/seguro/wos.key").read_text().strip()
incites_key = Path("/local/seguro/incites.key").read_text().strip()

pipeline = ClarivateResearchMetrics(
    wos_api_key=wos_key,
    incites_api_key=incites_key,
)
```

---

# 38. Considerações metodológicas

## ORCID

O ORCID é usado como identificador inicial, mas a qualidade da recuperação depende da associação correta do ORCID aos registros na Web of Science.

É recomendável verificar pesquisadores com:

```text
publication_count = 0
```

ou com baixa consistência no ResearcherID.

---

## ResearcherID

O ResearcherID é resolvido a partir das publicações recuperadas.

O campo:

```text
researcher_id_resolution_confidence
```

deve ser usado como indicador de auditoria, não como uma probabilidade estatística calibrada.

---

## Internacionalização

O pipeline produz diferentes sinais:

```text
incites_is_international_collab
is_international_wos
has_foreign_partner_inferred
```

Eles podem divergir em casos de:

- afiliações incompletas;
- diferentes versões dos metadados;
- múltiplas afiliações do mesmo autor;
- ausência de associação entre autor e endereço;
- critérios específicos da fonte.

Por isso, preservar os três indicadores é preferível a substituir todos por uma única variável.

---

## Mobilidade

A ocorrência de múltiplos países de afiliação pode representar:

- mobilidade acadêmica;
- dupla afiliação;
- vínculo simultâneo;
- mudança de instituição;
- inconsistência cadastral.

O indicador deve ser interpretado com contexto.

---

## CNCI e comparação de impacto

O CNCI é especialmente útil para comparação entre áreas, anos e tipos documentais, mas resultados agregados devem considerar:

- tamanho da produção;
- cobertura InCites;
- distribuição dos valores;
- outliers;
- composição disciplinar.

Por isso o pipeline preserva:

```text
mean
median
min
max
std
count
```

e não apenas a média.

---

# 39. Auditoria e reprodutibilidade

O desenho com dois Parquets permite separar:

```text
resultado agregado
        │
        ▼
researchers_metrics.parquet
```

de:

```text
origem das métricas
        │
        ▼
researcher_publications_metrics.parquet
```

Isso permite reconstruir e auditar praticamente todas as métricas agregadas.

Exemplo:

```python
import pandas as pd

researcher_name = "Nome do Pesquisador"

researchers = pd.read_parquet(
    "output/researchers_metrics.parquet"
)

publications = pd.read_parquet(
    "output/researcher_publications_metrics.parquet"
)

detail = publications[
    publications["researcher_name"] == researcher_name
]

print(detail)
```

---

# 40. Exemplo completo

```python
from clarivate_research_metrics import ClarivateResearchMetrics
import pandas as pd


researchers = [
    {
        "name": "Pesquisador A",
        "orcid": "0000-0000-0000-0000",
        "institution": "Minha Instituição",
    },
    {
        "name": "Pesquisador B",
        "orcid": "0000-0000-0000-000X",
        "institution": "Minha Instituição",
    },
]


pipeline = ClarivateResearchMetrics(
    wos_api_key="SUA_CHAVE_WOS_EXPANDED",
    researcher_api_key="SUA_CHAVE_RESEARCHER_API",
    incites_api_key="SUA_CHAVE_INCITES",

    incites_schemas=[
        "wos",
        "sdg",
        "ct",
        "esi",
        "fapesp",
        "capesl1",
        "capesl2",
        "capesl3",
        "oecd",
    ],

    include_researcher_profile=True,
    include_citation_report=True,
    include_raw_profile_json=True,
    include_raw_wos_json=False,

    verbose=True,
)


outputs = pipeline.run(
    input_json=researchers,
    start_year=2020,
    end_year=2026,
    output_dir="./clarivate_output",
)


df_researchers = pd.read_parquet(
    outputs["researchers_parquet"]
)

df_publications = pd.read_parquet(
    outputs["publications_parquet"]
)


print(
    df_researchers[
        [
            "researcher_name",
            "publication_count",
            "cnci_mean",
            "international_collaboration_incites_rate",
            "unique_foreign_partner_countries_count",
            "partner_country_diversity_shannon",
        ]
    ]
)
```

---

# 41. Fontes oficiais

Documentação consultada para as informações de acesso e licenciamento:

## Clarivate Developer Portal

```text
https://developer.clarivate.com/
```

## Developer Portal FAQ

```text
https://developer.clarivate.com/content/developer-portal-faq
```

## Web of Science API Expanded

```text
https://developer.clarivate.com/apis/wos
```

## Web of Science Researcher API

```text
https://developer.clarivate.com/apis/wos-researcher
```

## InCites Document Level Metrics API

```text
https://developer.clarivate.com/apis/incites
```

## Web of Science Starter API

```text
https://developer.clarivate.com/apis/wos-starter
```

---

# 42. Resumo

Para executar o pipeline completo:

```text
Entrada
  nome + ORCID
       │
       ▼
WoS Expanded
       │
       ├── publicações
       ├── autores
       ├── países
       ├── afiliações
       └── ResearcherID
       │
       ├──► Researcher API
       │       └── métricas do perfil
       │
       └──► InCites
               ├── impacto normalizado
               ├── internacionalização
               ├── colaboração
               ├── Open Access
               └── taxonomias
                       │
                       ▼
              dois arquivos Parquet
```

A arquitetura prioriza:

- rastreabilidade;
- granularidade publicação × pesquisador;
- métricas normalizadas de impacto;
- internacionalização;
- diversidade de parceiros;
- comparação entre produção internacional e doméstica;
- preservação das classificações completas;
- capacidade de auditoria das métricas agregadas.
