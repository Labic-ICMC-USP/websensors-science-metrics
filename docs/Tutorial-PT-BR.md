# Tutorial completo do WebSensors Science Metrics

Este tutorial apresenta a instalação, configuração, execução e auditoria do **WebSensors Science Metrics**, uma pipeline construída sobre o WebSensors Flow para coletar dados científicos do OpenAlex, construir um grafo de conhecimento no ArcadeDB, enriquecer identidades e afiliações e registrar a execução no MLflow.

O objetivo é permitir que um novo usuário clone ou descompacte o projeto e consiga reproduzir todo o fluxo localmente, incluindo os servidores auxiliares, os testes de infraestrutura e uma execução de exemplo com cinco pesquisadores do PPG-CCMC do ICMC-USP.

---

## 1. Visão geral do projeto

A pipeline começa com uma lista de pesquisadores informada em YAML. Para cada nome, o sistema busca os candidatos mais prováveis no OpenAlex, coleta perfis e produção científica, normaliza os dados e cria uma camada bruta no ArcadeDB.

Em seguida, a pipeline transforma os dados normalizados em um grafo de conhecimento e executa etapas de modelagem para resolver identidades, estimar a instituição principal dos pesquisadores e enriquecer os coautores usando a produção própria de cada um.

Ao final, o projeto gera duas visões complementares:

- uma camada de **relatórios tabulares**, com indicadores de produção e impacto;
- uma camada de **grafo**, com pesquisadores, coautores, instituições e relações de colaboração.

O MLflow registra a execução do pipeline, seus parâmetros, métricas, eventos, artefatos e registros detalhados produzidos pelos steps.

### 1.1. Fluxo completo

```text
Arquivo YAML com pesquisadores
          |
          v
01 - Ingestão OpenAlex
  top-N candidatos por pesquisador
  coleta de perfis, trabalhos e instituições
  normalização em authors / institutions / works
          |
          v
02 - Preprocessamento do KG
  criação de vértices e arestas brutas
  autoria, afiliação, candidatos e referências
          |
          v
03 - Resolução de identidade
  comparação entre candidatos
  criação de researcher_entities
  registro das evidências de merge
          |
          v
04 - Instituição principal
  frequência + recência + persistência
  fuzzy matching de instituições
          |
          v
05 - Enriquecimento de coautores
  busca das produções próprias recentes
  estimativa de instituição e país principais
          |
          v
06 - Reporting
  report_production
  report_group_summary
  COLLABORATES_WITH
          |
          +-------------------+
          |                   |
          v                   v
      ArcadeDB             MLflow
   dados + grafo      auditoria da execução
```

### 1.2. Princípio de separação entre dado bruto e dado inferido

O projeto evita sobrescrever a evidência original coletada no OpenAlex.

Os tipos `authors`, `institutions` e `works` representam a camada normalizada de origem. As entidades criadas posteriormente, como `researcher_entities`, `principal_institutions` e `coauthor_entities`, representam interpretações e inferências feitas pelos modelos do pipeline.

Essa separação é importante porque permite:

1. reexecutar um modelo de resolução de identidade sem recolher os dados brutos;
2. comparar versões diferentes do modelo;
3. auditar por que duas entidades foram ou não agrupadas;
4. trocar regras heurísticas por modelos de aprendizado de máquina no futuro;
5. integrar outras fontes sem destruir a proveniência original.

---

## 2. Pré-requisitos

O tutorial assume Linux ou macOS.

Requisitos principais:

- Python 3.10 ou superior;
- Java 21 recomendado para a distribuição atual do ArcadeDB;
- `curl` para alguns testes e inspeções manuais;
- acesso à internet para consultar o OpenAlex e baixar dependências.

Verifique o ambiente:

```bash
python3 --version
java -version
curl --version
```

Para uma coleta real no OpenAlex, recomenda-se configurar uma chave de API:

```bash
export OPENALEX_API_KEY="sua-chave"
```

A pipeline também aceita a chave diretamente no YAML, mas uma variável de ambiente evita gravar credenciais em arquivos versionados.

---

## 3. Instalação geral do projeto

Descompacte o pacote e entre no diretório:

```bash
unzip websensors-science-metrics.zip
cd websensors-science-metrics
```

Execute a preparação local:

```bash
./scripts/setup_local.sh
```

O script cria o ambiente Python dentro do próprio projeto, instala as dependências e instala o ArcadeDB localmente.

A estrutura principal após a instalação será semelhante a:

```text
websensors-science-metrics/
├── .venv/
├── .runtime/
│   ├── arcadedb/
│   ├── arcadedb-data/
│   ├── mlflow/
│   └── logs/
├── docs/
├── flows/
├── outputs/
├── scripts/
├── src/
├── tests/
├── mkdocs.yml
├── README.md
└── Tutorial-PT-BR.md
```

Ative o ambiente Python quando for executar comandos manualmente:

```bash
source .venv/bin/activate
```

Teste a instalação Python:

```bash
python -m pytest
```

---

# Parte I — ArcadeDB

## 4. Instalação do ArcadeDB

O comando padrão é:

```bash
./scripts/install_arcadedb.sh
```

O instalador baixa uma distribuição binária e a extrai em:

```text
.runtime/arcadedb/
```

Os bancos criados pelo projeto ficam em:

```text
.runtime/arcadedb-data/
```

### 4.1. Instalação offline

Caso o servidor não tenha acesso ao GitHub, baixe o pacote do ArcadeDB em outra máquina e execute:

```bash
ARCADEDB_ARCHIVE=/caminho/arcadedb-x.y.z.tar.gz \
  ./scripts/install_arcadedb.sh
```

Também é possível fornecer uma URL específica:

```bash
ARCADEDB_DOWNLOAD_URL="https://servidor/arcadedb-x.y.z.tar.gz" \
  ./scripts/install_arcadedb.sh
```

---

## 5. Iniciando o ArcadeDB

Defina a senha local:

```bash
export ARCADEDB_PASSWORD="playwithdata"
```

Inicie o servidor:

```bash
./scripts/start_arcadedb.sh
```

A saída informa o PID, a URL e o arquivo de log.

Configuração padrão deste projeto:

```text
URL: http://127.0.0.1:2480
Usuário: root
Senha: valor de ARCADEDB_PASSWORD
Log: .runtime/logs/arcadedb.log
```

Acompanhe o log em outro terminal:

```bash
tail -f .runtime/logs/arcadedb.log
```

---

## 6. Testando o ArcadeDB

Execute o smoke test:

```bash
./scripts/test_arcadedb.sh
```

Esse teste:

1. verifica se o servidor responde;
2. cria um banco temporário;
3. cria um tipo de documento;
4. grava um registro;
5. lê o registro novamente;
6. remove o banco temporário.

Uma execução bem-sucedida termina com uma mensagem semelhante a:

```text
Leitura e escrita no banco temporário concluídas com sucesso.
Banco temporário removido. ArcadeDB está pronto para o pipeline.
```

Para encerrar o servidor:

```bash
./scripts/stop_arcadedb.sh
```

---

# Parte II — MLflow

## 7. Instalando o MLflow

O `setup_local.sh` instala o conjunto completo de dependências. Em um ambiente existente, o MLflow pode ser instalado separadamente com:

```bash
./scripts/install_mlflow.sh
```

Confirme a instalação:

```bash
.venv/bin/mlflow --version
```

O projeto utiliza o MLflow como servidor de tracking e auditoria da execução. O banco de metadados e os artefatos ficam dentro do próprio diretório do projeto.

---

## 8. Iniciando o MLflow

Execute:

```bash
./scripts/start_mlflow.sh
```

Configuração local padrão:

```text
UI: http://127.0.0.1:5000
Backend: .runtime/mlflow/mlflow.db
Artefatos: .runtime/mlflow/artifacts/
Log: .runtime/logs/mlflow.log
```

Acompanhe o log:

```bash
tail -f .runtime/logs/mlflow.log
```

---

## 9. Testando o MLflow

Execute:

```bash
./scripts/test_mlflow.sh
```

O teste verifica o endpoint de versão do servidor, cria o experimento:

```text
websensors-science-metrics-smoke-test
```

e registra uma execução contendo um parâmetro e uma métrica.

Abra no navegador:

```text
http://127.0.0.1:5000
```

Na interface do MLflow:

1. localize **Experiments** no menu lateral;
2. abra `websensors-science-metrics-smoke-test`;
3. clique na execução `smoke-test`;
4. confirme a presença do parâmetro `component=mlflow`;
5. confirme a métrica `ok=1`.

Para encerrar:

```bash
./scripts/stop_mlflow.sh
```

---

# Parte III — Servidor de documentação

## 10. Executando a documentação local

As docstrings dos módulos do projeto são publicadas com MkDocs e MkDocstrings.

Inicie o servidor:

```bash
./scripts/start_docs.sh
```

Abra:

```text
http://127.0.0.1:8000
```

A documentação inclui:

- este tutorial completo;
- arquitetura do projeto;
- mapeamento entre o frontend v11 e a nova pipeline;
- referência automática das classes e funções Python;
- código-fonte dos componentes documentados.

Para verificar se a documentação compila sem erros:

```bash
source .venv/bin/activate
mkdocs build --strict
```

---

# Parte IV — Configuração do pipeline

## 11. Arquivo principal de configuração

O arquivo padrão é:

```text
flows/science_metrics/flow.yaml
```

Para este tutorial, use o arquivo já incluído:

```text
flows/science_metrics/flow.ppg-ccmc-tutorial.yaml
```

Esse arquivo analisa cinco pesquisadores do PPG-CCMC do ICMC-USP:

- Ricardo Marcondes Marcacini;
- Solange Oliveira Rezende;
- Alneu de Andrade Lopes;
- Adenilso da Silva Simão;
- Agma Juci Machado Traina.

O exemplo usa apenas nome e pistas institucionais. Isso é proposital, pois permite testar a busca dos `top-N` candidatos e a etapa de resolução de identidade.

### 11.1. Bloco completo dos pesquisadores

```yaml
pipeline:
  params:
    group:
      name: "ppg_ccmc_tutorial"
      researchers:
        - name: "Ricardo Marcondes Marcacini"
          institution_hint: "Universidade de São Paulo"
          country_hint: "BR"

        - name: "Solange Oliveira Rezende"
          institution_hint: "Universidade de São Paulo"
          country_hint: "BR"

        - name: "Alneu de Andrade Lopes"
          institution_hint: "Universidade de São Paulo"
          country_hint: "BR"

        - name: "Adenilso da Silva Simão"
          institution_hint: "Universidade de São Paulo"
          country_hint: "BR"

        - name: "Agma Juci Machado Traina"
          institution_hint: "Universidade de São Paulo"
          country_hint: "BR"
```

### 11.2. Configuração do ArcadeDB

```yaml
arcadedb:
  base_url: "http://127.0.0.1:2480"
  username: "root"
  password_env: "ARCADEDB_PASSWORD"
  password: "playwithdata"
  recreate_on_run: true
  timeout_seconds: 45
  readiness_attempts: 20
  readiness_delay_seconds: 1
```

O campo:

```yaml
recreate_on_run: true
```

faz com que o banco do grupo seja removido e recriado no início da ingestão. Isso é útil durante o desenvolvimento porque garante que uma nova execução comece com estado limpo.

Neste tutorial, o banco criado será:

```text
ppg_ccmc_tutorial
```

### 11.3. Configuração do OpenAlex

```yaml
openalex:
  base_url: "https://api.openalex.org"
  api_key_env: "OPENALEX_API_KEY"
  api_key: ""
  mailto: ""
  top_n_candidates: 5
  start_year: 2015
  end_year: 2026
  per_page: 200
  max_pages_per_candidate: 20
  request_delay_ms: 120
  timeout_seconds: 45
  max_institutions_to_enrich: 500
  max_sources_to_enrich: 300
  coauthor_recent_works: 10
  max_external_coauthors: 50
```

Para uma primeira execução, `max_external_coauthors: 50` limita o enriquecimento e reduz o tempo de coleta.

Depois de validar o fluxo, use:

```yaml
max_external_coauthors: 0
```

para processar todos os coautores encontrados.

### 11.4. Configuração da resolução de identidade

```yaml
modeling:
  entity_resolution:
    merge_threshold: 0.72
    evidence_edge_threshold: 0.55
    selection_ambiguity_margin: 0.08
    allow_cross_seed_merge: true
    weight_name: 0.25
    weight_work_overlap: 0.28
    weight_doi_overlap: 0.17
    weight_coauthor_overlap: 0.12
    weight_institution_overlap: 0.08
    weight_topic_overlap: 0.05
    weight_country_overlap: 0.03
    weight_same_seed: 0.02
    conflicting_orcid_score_cap: 0.44
```

Esses pesos controlam quanto cada evidência contribui para a decisão de similaridade entre dois perfis candidatos.

---

# Parte V — Entendendo cada step

## 12. Step 01 — Ingestão dos dados

Classe:

```text
projects.science_metrics.steps.IngestDataStep
```

Responsabilidades:

1. ler a lista de pesquisadores do YAML;
2. buscar os `top_n_candidates` autores mais prováveis no OpenAlex;
3. manter todos os candidatos para análise posterior;
4. coletar produção científica no intervalo configurado;
5. coletar autores, coautores, instituições, fontes e metadados;
6. normalizar os dados;
7. criar o banco ArcadeDB do grupo;
8. criar o schema inicial;
9. persistir `authors`, `institutions` e `works`.

A ingestão não decide definitivamente qual candidato corresponde ao pesquisador informado. Essa decisão fica para o step de resolução de identidade.

---

## 13. Step 02 — Preprocessamento e construção do KG bruto

Classe:

```text
projects.science_metrics.steps.PreprocessKnowledgeGraphStep
```

O step transforma as tabelas normalizadas em uma representação explicitamente orientada a grafo.

Principais vértices:

```text
authors
institutions
works
researcher_seeds
```

Principais arestas:

```text
AUTHORED
AFFILIATED_WITH
ASSOCIATED_WITH_INSTITUTION
CITES
CANDIDATE_FOR
```

Essa camada ainda representa evidências brutas. Não existe, nesse ponto, uma entidade canônica única para cada pesquisador.

---

## 14. Step 03 — Resolução de identidade

Classe:

```text
projects.science_metrics.steps.ResolveResearcherIdentityStep
```

O modelo compara candidatos usando evidências como:

- ORCID;
- similaridade de nome;
- trabalhos em comum;
- DOIs em comum;
- coautores em comum;
- instituições em comum;
- tópicos em comum;
- país;
- origem na mesma semente de busca.

O resultado cria:

```text
researcher_entities
```

A ligação entre perfil bruto e entidade canônica é:

```text
authors -[RESOLVED_AS]-> researcher_entities
```

As evidências de similaridade ficam registradas em:

```text
SAME_AS_EVIDENCE
```

Mesmo quando um pesquisador tem apenas um perfil candidato válido, é criada uma entidade canônica nova. Isso mantém a separação entre a camada bruta e a camada modelada.

---

## 15. Step 04 — Inferência da instituição principal

Classe:

```text
projects.science_metrics.steps.InferPrincipalInstitutionStep
```

O modelo atual combina quatro sinais simples e auditáveis:

- frequência de trabalhos associados à instituição;
- frequência ponderada por recência;
- persistência da afiliação ao longo dos anos;
- presença da instituição na produção mais recente.

Nomes institucionais semelhantes podem ser agrupados por fuzzy matching.

O resultado cria:

```text
principal_institutions
```

com relações como:

```text
researcher_entities -[HAS_PRIMARY_INSTITUTION]-> principal_institutions
principal_institutions -[DERIVED_FROM_INSTITUTION]-> institutions
```

---

## 16. Step 05 — Enriquecimento dos coautores

Classe:

```text
projects.science_metrics.steps.EnrichCoauthorsStep
```

Esse step resolve uma limitação importante de análises bibliométricas simplificadas.

Um coautor pode aparecer em apenas um artigo com o grupo principal. Se a instituição desse artigo for usada isoladamente para classificar sua instituição ou seu país, a inferência pode estar errada.

Por isso, a pipeline consulta novamente cada coautor e recupera suas próprias produções recentes.

Esses trabalhos adicionais são usados apenas como evidência para estimar:

- instituição principal;
- país principal.

Eles não entram na tabela de produção intelectual do grupo analisado.

O resultado cria:

```text
coauthor_entities
```

---

## 17. Step 06 — Reporting

Classe:

```text
projects.science_metrics.steps.BuildScienceMetricsReportsStep
```

Esse step materializa as estruturas finais para análise.

### `report_production`

Uma linha por trabalho pertencente à produção dos pesquisadores selecionados.

Inclui, entre outros campos:

- título;
- DOI;
- ano;
- tipo;
- citações;
- FWCI;
- percentis;
- indicadores de top 1% e top 10%;
- open access;
- fonte de publicação;
- tópico principal;
- autores do grupo;
- coautores;
- instituições;
- países;
- classificação nacional ou internacional.

### `report_group_summary`

Resumo agregado do grupo.

Inclui:

- número de publicações;
- total de citações;
- h-index da produção coletada;
- FWCI médio;
- indicadores dos veículos;
- percentual de open access;
- percentual de trabalhos top 10%;
- produção nacional e internacional;
- número de coautores;
- número de países;
- número de instituições;
- número de relações de colaboração.

### Grafo de colaboração

As relações finais são criadas entre entidades resolvidas:

```text
researcher_entities -[COLLABORATES_WITH]- researcher_entities
researcher_entities -[COLLABORATES_WITH]- coauthor_entities
```

---

# Parte VI — Executando o exemplo do PPG-CCMC

## 18. Subindo os serviços

Terminal 1:

```bash
cd websensors-science-metrics
export ARCADEDB_PASSWORD="playwithdata"
./scripts/start_arcadedb.sh
./scripts/test_arcadedb.sh
```

Terminal 2:

```bash
cd websensors-science-metrics
./scripts/start_mlflow.sh
./scripts/test_mlflow.sh
```

Configure a chave do OpenAlex no terminal onde o pipeline será executado:

```bash
export OPENALEX_API_KEY="sua-chave"
export ARCADEDB_PASSWORD="playwithdata"
```

---

## 19. Executando a pipeline

Ative o ambiente:

```bash
source .venv/bin/activate
```

Execute:

```bash
websensors-science-metrics \
  --config flows/science_metrics/flow.ppg-ccmc-tutorial.yaml
```

O pipeline executa os seis steps em sequência.

Ao final, a saída do terminal apresenta:

- status geral da execução;
- estatísticas por etapa;
- nome do banco ArcadeDB;
- URL do ArcadeDB Studio;
- consultas úteis para os relatórios;
- consulta OpenCypher para o grafo de colaboração.

Os relatórios locais do WebSensors Flow são gravados em:

```text
outputs/ppg_ccmc_tutorial/reports/
```

---

# Parte VII — Auditoria no MLflow

## 20. Abrindo a execução

Abra:

```text
http://127.0.0.1:5000
```

No menu lateral:

1. clique em **Experiments**;
2. selecione `websensors-science-metrics-ppg-ccmc`;
3. abra a execução chamada `ppg-ccmc-tutorial`.

O WebSensors Flow também executa uma verificação de preflight antes do pipeline. Por isso, pode aparecer uma execução de teste com prefixo semelhante a:

```text
websensors-flow-preflight
```

Ela serve apenas para confirmar que o observador MLflow consegue gravar dados antes de a pipeline real começar.

---

## 21. O que auditar no MLflow

### 21.1. Parameters

Use a área de parâmetros para conferir a configuração efetivamente usada na execução.

Exemplos de aspectos importantes:

- ambiente;
- nome do projeto;
- parâmetros declarados pelos steps;
- limites de coleta;
- parâmetros de modelagem.

### 21.2. Metrics

As métricas permitem comparar execuções diferentes.

Exemplos típicos:

- quantidade de pesquisadores-semente;
- quantidade de candidatos OpenAlex;
- quantidade de autores normalizados;
- quantidade de trabalhos;
- quantidade de instituições;
- quantidade de entidades resolvidas;
- quantidade de coautores enriquecidos;
- quantidade de registros finais.

### 21.3. Artifacts

Na aba de artefatos, procure especialmente:

```text
configuration/
events/
metric_records/
step_metadata/
step_text/
```

A pasta `configuration/` guarda a configuração resolvida do fluxo e dos steps.

A pasta `events/` registra a sequência estruturada de eventos do pipeline.

A pasta `metric_records/` contém registros detalhados produzidos pelos steps. Essa área é particularmente útil para auditar candidatos, entidades ou coautores individualmente.

### 21.4. Comparando duas execuções

Uma forma prática de evoluir os modelos é:

1. executar a pipeline com uma configuração de pesos;
2. alterar apenas um conjunto de parâmetros;
3. executar novamente;
4. selecionar as duas runs no MLflow;
5. comparar métricas e artefatos.

Isso é útil, por exemplo, para estudar o efeito de diferentes valores de:

```yaml
merge_threshold
evidence_edge_threshold
weight_name
weight_work_overlap
fuzzy_threshold
recency_decay
```

---

# Parte VIII — Analisando os resultados no ArcadeDB

## 22. Acessando o ArcadeDB Studio

Abra no navegador:

```text
http://127.0.0.1:2480
```

Faça login com:

```text
Usuário: root
Senha: valor configurado em ARCADEDB_PASSWORD
```

Selecione o banco:

```text
ppg_ccmc_tutorial
```

Dependendo da versão do Studio, o seletor do banco pode aparecer na tela inicial ou no topo da área de trabalho após o login.

---

## 23. Explorando o schema

No menu lateral do Studio, abra a área **Database** ou **Schema**.

Procure os tipos de vértice:

```text
authors
institutions
works
researcher_seeds
researcher_entities
principal_institutions
coauthor_entities
```

Procure os tipos de documento:

```text
report_production
report_group_summary
```

Procure as arestas:

```text
AUTHORED
AFFILIATED_WITH
ASSOCIATED_WITH_INSTITUTION
CITES
CANDIDATE_FOR
SAME_AS_EVIDENCE
RESOLVED_AS
REPRESENTS_RESEARCHER
HAS_PRIMARY_INSTITUTION
DERIVED_FROM_INSTITUTION
RESOLVED_AS_COAUTHOR
COLLABORATES_WITH
```

Essa inspeção é uma boa primeira verificação de que todos os steps foram executados.

---

## 24. Consultando o resumo do grupo

Abra **Query** no menu lateral.

Selecione a linguagem SQL e execute:

```sql
SELECT FROM report_group_summary
```

Esse registro contém o resumo agregado da execução.

---

## 25. Consultando a produção intelectual

Na área **Query**, execute:

```sql
SELECT FROM report_production
ORDER BY publication_year DESC
```

Para limitar a saída:

```sql
SELECT FROM report_production
ORDER BY publication_year DESC
LIMIT 50
```

Para consultar apenas trabalhos internacionais:

```sql
SELECT FROM report_production
WHERE collaboration_scope = 'internacional'
ORDER BY publication_year DESC
```

---

## 26. Auditando os pesquisadores selecionados

Execute:

```sql
SELECT FROM researcher_entities
WHERE selected = true
```

Observe principalmente:

- `entity_id`;
- nome canônico;
- IDs de autores brutos associados;
- evidências de seleção;
- possíveis indicadores de ambiguidade.

Depois consulte as evidências de similaridade:

```sql
SELECT FROM SAME_AS_EVIDENCE
ORDER BY score DESC
```

Para uma auditoria aprofundada, compare essas arestas com os vértices `authors` ligados às entidades resolvidas.

---

## 27. Auditando instituições principais

Execute:

```sql
SELECT FROM principal_institutions
ORDER BY display_name
```

Para verificar as ligações entre pesquisadores e instituições, use OpenCypher:

```cypher
MATCH (r:researcher_entities)-[e:HAS_PRIMARY_INSTITUTION]->(i:principal_institutions)
WHERE r.selected = true
RETURN r,e,i
```

Na visualização de resultados, altere para o modo de grafo quando o Studio disponibilizar essa opção.

---

## 28. Visualizando o grafo de colaboração

Na área **Query**:

1. escolha **OpenCypher** como linguagem;
2. execute:

```cypher
MATCH (r:researcher_entities)-[e:COLLABORATES_WITH]-(n)
WHERE r.selected = true
RETURN r,e,n
```

Depois selecione a visualização em grafo.

Para reduzir o tamanho inicial:

```cypher
MATCH (r:researcher_entities)-[e:COLLABORATES_WITH]-(n)
WHERE r.selected = true AND e.works_count >= 2
RETURN r,e,n
LIMIT 200
```

Uma análise recomendada é inspecionar:

- quais pesquisadores do grupo aparecem mais conectados;
- quais coautores externos têm maior recorrência;
- quais instituições aparecem como pontes;
- quais colaborações são nacionais e internacionais;
- quais arestas dependem de poucas publicações e merecem auditoria manual.

---

# Parte IX — Relação entre MLflow e ArcadeDB

## 29. Como usar os dois sistemas juntos

O ArcadeDB responde à pergunta:

> Qual é o estado atual dos dados, entidades, relações e indicadores produzidos pela pipeline?

O MLflow responde à pergunta:

> Como esse estado foi produzido, com quais parâmetros, métricas, eventos e artefatos de execução?

Uma auditoria completa deve combinar ambos.

Exemplo:

1. encontre uma entidade suspeita em `researcher_entities` no ArcadeDB;
2. identifique a execução responsável pela criação do banco;
3. abra a run correspondente no MLflow;
4. consulte os registros e artefatos da etapa `03_resolve_identity`;
5. verifique os scores e evidências usados pelo modelo;
6. altere os parâmetros do YAML, se necessário;
7. execute novamente e compare as runs no MLflow.

---

# Parte X — Desenvolvimento e testes

## 30. Executando os testes unitários

```bash
source .venv/bin/activate
pytest
```

Para saída detalhada:

```bash
pytest -vv
```

Os testes atuais cobrem principalmente:

- resolução de entidades;
- inferência de instituição principal;
- configuração;
- métricas auxiliares.

---

## 31. Validando a documentação

```bash
source .venv/bin/activate
mkdocs build --strict
```

Para desenvolvimento interativo:

```bash
./scripts/start_docs.sh
```

Ao alterar uma docstring ou página Markdown, o MkDocs recarrega a documentação no navegador.

---

# Parte XI — Próximos passos e limitações conhecidas

## 32. Resolução de identidade ainda baseada em heurísticas

A resolução atual utiliza uma combinação ponderada de sinais definidos manualmente.

Melhorias possíveis:

- treinar um classificador supervisionado de pares de autores;
- aprender os pesos a partir de exemplos rotulados;
- usar modelos probabilísticos para produzir uma probabilidade calibrada de identidade;
- usar aprendizado ativo para encaminhar apenas os casos ambíguos à revisão humana;
- explorar embeddings de nomes, títulos, tópicos e trajetórias científicas;
- usar grafos neurais para incorporar a estrutura de coautoria e afiliação.

---

## 33. Instituição principal simplifica trajetórias acadêmicas

O conceito de uma única instituição principal é útil para relatórios agregados, mas pode esconder mudanças legítimas de afiliação ao longo do tempo.

Melhorias possíveis:

- criar afiliações por intervalo temporal;
- detectar mudanças de instituição;
- representar múltiplas afiliações simultâneas;
- diferenciar vínculo permanente, visitante e colaboração;
- usar evidências de fontes institucionais externas.

---

## 34. Enriquecimento dos coautores pode ser expandido

A versão atual usa as produções recentes do próprio coautor para estimar instituição e país.

Melhorias possíveis:

- aumentar dinamicamente a janela de trabalhos quando a evidência for insuficiente;
- aplicar a mesma resolução de identidade completa aos coautores;
- detectar perfis duplicados de coautores;
- usar afiliação temporal em vez de uma instituição única;
- priorizar enriquecimento apenas para coautores relevantes em grandes grafos.

---

## 35. Integração com outras bases

O OpenAlex é uma fonte rica, mas não deve ser considerado a única fonte de verdade.

Uma evolução natural é cruzar o KG com outras bases.

### CNPq e Currículo Lattes

Possíveis contribuições:

- nome completo e variações de nome;
- vínculo institucional declarado;
- formação acadêmica;
- projetos;
- orientações;
- produção não indexada no OpenAlex;
- identificadores adicionais.

### Plataforma Sucupira e dados da CAPES

Possíveis contribuições:

- vínculo com programas de pós-graduação;
- categoria docente;
- programa e instituição de atuação;
- produção declarada pelo programa;
- linhas de pesquisa;
- teses e dissertações;
- contexto institucional para desambiguação.

Essas integrações devem preservar a proveniência. Em vez de substituir os dados do OpenAlex, o ideal é criar novas evidências e relações no KG.

---

## 36. Uso de aprendizado de máquina

O projeto foi construído para permitir que regras heurísticas sejam substituídas gradualmente por modelos aprendidos.

Aplicações possíveis:

- entity resolution supervisionada;
- classificação de instituição principal;
- detecção de anomalias em perfis;
- previsão de links de colaboração;
- classificação temática;
- agrupamento de trajetórias científicas;
- identificação de comunidades no grafo;
- recomendação de potenciais colaboradores.

O MLflow já oferece a base de rastreabilidade necessária para comparar versões desses modelos.

---

## 37. Uso de LLMs

Modelos de linguagem podem atuar como uma camada adicional de enriquecimento, especialmente nos casos em que os metadados estruturados são insuficientes.

Possibilidades:

- analisar evidências conflitantes de identidade;
- explicar por que dois perfis provavelmente representam a mesma pessoa;
- normalizar nomes institucionais complexos;
- extrair afiliações de textos não estruturados;
- classificar tópicos e áreas de pesquisa;
- produzir justificativas auditáveis para decisões do pipeline;
- apoiar curadoria humana em casos de baixa confiança.

LLMs não devem substituir as evidências originais. O ideal é registrar a saída do modelo como uma nova evidência, incluindo modelo utilizado, prompt, versão, score e contexto.

---

## 38. Evolução do Knowledge Graph

O KG pode ser enriquecido com novas entidades e relações.

Exemplos:

- programas de pós-graduação;
- áreas de avaliação;
- linhas de pesquisa;
- projetos financiados;
- agências de fomento;
- orientações;
- teses e dissertações;
- eventos científicos;
- periódicos e conferências;
- tópicos e macrotemas;
- organizações;
- países e regiões.

Também é possível criar propriedades temporais, embeddings vetoriais e relações inferidas por modelos.

---

## 39. Limitações operacionais

A execução depende da qualidade e disponibilidade da API do OpenAlex.

Em grupos grandes, os principais custos são:

- busca dos candidatos;
- coleta das produções;
- enriquecimento de instituições e fontes;
- reconsulta dos coautores.

Melhorias futuras podem incluir:

- cache local das respostas do OpenAlex;
- ingestão incremental;
- paralelização controlada;
- checkpoints por step;
- reuso de entidades já resolvidas entre grupos;
- fila de enriquecimento assíncrona;
- políticas explícitas de atualização temporal.

---

# Parte XII — Comandos de referência rápida

## 40. Preparar o ambiente

```bash
./scripts/setup_local.sh
```

## 41. Iniciar e testar ArcadeDB

```bash
export ARCADEDB_PASSWORD="playwithdata"
./scripts/start_arcadedb.sh
./scripts/test_arcadedb.sh
```

## 42. Iniciar e testar MLflow

```bash
./scripts/start_mlflow.sh
./scripts/test_mlflow.sh
```

## 43. Executar o tutorial

```bash
export OPENALEX_API_KEY="sua-chave"
export ARCADEDB_PASSWORD="playwithdata"
source .venv/bin/activate
websensors-science-metrics \
  --config flows/science_metrics/flow.ppg-ccmc-tutorial.yaml
```

## 44. Abrir as interfaces

```text
ArcadeDB Studio: http://127.0.0.1:2480
MLflow:          http://127.0.0.1:5000
Documentação:    http://127.0.0.1:8000
```

## 45. Iniciar a documentação

```bash
./scripts/start_docs.sh
```

## 46. Parar os serviços

```bash
./scripts/stop_mlflow.sh
./scripts/stop_arcadedb.sh
```

---

## Referências técnicas

- Documentação oficial do ArcadeDB: https://docs.arcadedb.com/
- ArcadeDB Studio: https://docs.arcadedb.com/arcadedb/tools/studio/main.html
- Documentação oficial do MLflow: https://mlflow.org/docs/latest/
- MLflow Tracking Server: https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/
- OpenAlex Developers: https://developers.openalex.org/
