# WebSensors Science Metrics

Demo estática em HTML5, JavaScript e CSS para análise de produção científica a partir de um endpoint compatível com OpenAlex.

## Como executar

```bash
unzip websensors-science-metrics-v5.zip
cd websensors-science-metrics
python3 -m http.server 8080
```

Depois acesse:

```text
http://localhost:8080
```

Evite abrir diretamente via `file://`, pois o navegador pode bloquear a leitura do `config.json`.

## Principais recursos da versão v5

- Interface com fundo branco e logo WebSensors em destaque.
- Tela de configuração da sessão com endpoint, API key, e-mail, limites de paginação e parâmetros de coleta.
- Busca de autores.
- Criação de grupo em sessão.
- Merge de múltiplas entradas do mesmo autor.
- Escolha manual da instituição principal quando o merge envolve instituições diferentes.
- Coleta de publicações por período.
- Deduplicação de publicações por identificador.
- Enriquecimento dos veículos para recuperar impacto, h-index e i10-index quando disponíveis.
- Filtros por tipo de publicação, tipo de veículo e acesso aberto.
- Dashboard geral com produção, citações, FWCI, h-index do conjunto, top 10%, acesso aberto, impacto e h-index dos veículos e séries temporais.
- Painel estratégico de internacionalização com apenas dois grupos:
  - apenas nacional;
  - internacional.
- Mapa coroplético mundial por país, com intensidade de colaboração internacional e fallback SVG caso a biblioteca cartográfica externa não carregue.
- Tabela de instituições com bandeira do país e filtro nacional/internacional.
- Painel temático por tópico, subárea, área e domínio.
- Indicadores temáticos com FWCI, h-index, citações, top 10% e tipos de publicação.
- Grafo de colaboração com zoom, pessoas do grupo, coautores externos nacionais e coautores externos internacionais em cores diferentes.
- Modais internos para detalhes. Títulos com DOI abrem o DOI em nova janela; os demais detalhes ficam dentro do sistema.
- Exportação em JSON e CSV.

## Novidades da v5

- Corrigido o tratamento de métricas ausentes: valores `null` não são mais convertidos indevidamente para zero.
- O FWCI é lido diretamente do objeto da publicação, inclusive para trabalhos em conferências.
- Adicionado filtro de acesso aberto nas telas de publicações, dashboard e tópicos.
- Adicionados o h-index dos veículos na tabela de publicações e um painel de veículos com produção, impacto e h-index.
- O mapa de internacionalização passou a usar um mapa coroplético mundial por país, mais adequado para dados agregados geograficamente.
- A identificação de países também aproveita os países das autorias quando disponíveis, além dos códigos das instituições.
- A lista de países é renderizada independentemente do mapa, evitando que uma falha cartográfica esconda os rankings.
- Os IDs dos nós do grafo são sempre exibidos verticalmente, um por linha, inclusive quando o nó representa apenas um perfil.

## Configuração

A configuração inicial fica em `config.json`:

```json
{
  "systemName": "Science Metrics",
  "logoUrl": "https://websensors.icmc.usp.br/assets/img/logo.png",
  "openAlex": {
    "baseUrl": "https://api.openalex.org",
    "authorsEndpoint": "/authors",
    "worksEndpoint": "/works",
    "sourcesEndpoint": "/sources",
    "apiKey": "",
    "mailto": "",
    "perPage": 200,
    "maxPagesPerAuthor": 10,
    "requestDelayMs": 250,
    "maxSourcesToEnrich": 150,
    "maxExternalCoauthors": 80
  },
  "defaults": {
    "startYear": 2020,
    "endYear": 2026,
    "countryBrazil": "BR"
  }
}
```

A tela de configuração sobrescreve esses valores apenas na sessão do navegador, usando `sessionStorage`.

## Internacionalização

A classificação da versão v5 usa somente dois grupos:

- **Apenas nacional**: nenhuma instituição estrangeira foi detectada nas afiliações da publicação.
- **Internacional**: pelo menos uma instituição estrangeira foi detectada nas afiliações da publicação.

A tabela de instituições mostra o ícone do país, o nome da instituição, o escopo nacional/internacional e a frequência nas publicações. O filtro por rádio permite alternar entre todas, nacionais e internacionais.

## Tópicos e áreas

O painel temático usa os campos de tópico das publicações. O usuário pode alternar entre:

- tópico;
- subárea;
- área;
- domínio.

Para cada agrupamento, o sistema calcula:

- publicações;
- participação percentual;
- FWCI médio;
- h-index dentro do conjunto analisado;
- citações médias;
- percentual top 10%;
- tipos de publicação mais frequentes.

## Merge de autores

Na busca de autores, selecione duas ou mais entradas e clique em **Mesclar selecionados**.

O sistema cria um autor consolidado dentro do grupo. Durante a coleta, ele consulta todos os perfis originais e deduplica as publicações no resultado final.

Quando há diferentes instituições entre os perfis selecionados, a aplicação pede qual instituição deve representar o autor no grupo.

## Observações

- Esta é uma demo front-end, sem backend e sem login.
- O grupo permanece vivo apenas na sessão do navegador.
- Grandes grupos podem gerar muitas chamadas à API.
- A API key fica visível no navegador, como em qualquer aplicação puramente front-end.
- O impacto do veículo usa `summary_stats.2yr_mean_citedness` quando disponível.
- O h-index por tópico é calculado dentro das publicações carregadas na sessão, não é o h-index global do tópico.
- O mapa usa polígonos mundiais simplificados incluídos no próprio projeto. Quando Leaflet está disponível, o mapa é interativo; caso contrário, a aplicação usa automaticamente a mesma base geográfica em SVG.

## Estrutura

```text
websensors-science-metrics/
├── index.html
├── config.json
├── css/
│   └── styles.css
├── js/
│   ├── app.js
│   ├── charts.js
│   ├── config.js
│   ├── graph.js
│   ├── metrics.js
│   ├── openalex-api.js
│   ├── store.js
│   └── world-countries.js
└── README.md
```

## Alterações da versão 6

- mapa de internacionalização renderizado diretamente em SVG a partir do GeoJSON embarcado, sem depender de tiles ou da inicialização do Leaflet em uma aba oculta;
- mapa coroplético interativo com intensidade por país, resumo dos principais parceiros e detalhe ao passar o mouse/clicar;
- contagem de países reforçada usando países do trabalho, instituições e autorias normalizadas;
- tipo de produção prioriza `primary_location.raw_type`, preservando categorias como `journal-article`, `proceedings-article` e `dissertation`;
- quando `primary_location.source` não existe, o sistema usa `primary_location.raw_source_name` como nome do veículo.

## Alterações da versão 7

- O mapa de internacionalização é sempre renderizado, mesmo quando não existem publicações internacionais no recorte atual.
- Países sem internacionalização usam cinza médio e fronteiras sólidas mais escuras para preservar a leitura completa do mapa-múndi.
- O parser de FWCI foi reforçado para aceitar valores numéricos em diferentes estruturas de resposta compatíveis com OpenAlex.
- A consolidação de publicações duplicadas preserva a representação que contém FWCI e outros metadados válidos, em vez de manter cegamente o primeiro registro recebido.
- Trabalhos de conferência (`proceedings-article`/`conference`) que ainda chegarem sem FWCI podem ser reconsultados individualmente para recuperar a representação completa do Work.
- `primary_location.raw_source_name` continua sendo usado como nome do veículo quando `primary_location.source` é nulo.

## Alterações da versão 8

- Correção da identidade dos nós no grafo de coautoria: autores externos sem ID bibliográfico não são mais colapsados em um único nó.
- Arestas são deduplicadas por par de autores e Work, evitando ligações artificiais e contagem duplicada.
- Instituições dos nós são agregadas diretamente das autorias das publicações em que cada pessoa aparece.
- O painel lateral do nó mostra instituições identificadas e a lista das publicações associadas ao autor na rede.


## Alterações da versão 10

- A nacionalidade de cada autor/coautor agora é resolvida uma única vez por `país principal`.
- A regra é global e compartilhada por internacionalização, mapa, ranking de países, tabelas e grafo.
- Se o país principal do coautor for `BR`, ele é nacional em todo o sistema, mesmo que existam afiliações estrangeiras secundárias em publicações específicas.
- O país principal é escolhido pela frequência das afiliações observadas; em empate com o Brasil, `BR` é priorizado. Para autores do grupo, a instituição principal selecionada pelo usuário tem prioridade.
- Uma publicação é classificada como internacional quando possui ao menos um autor/coautor cujo país principal resolvido é estrangeiro.


## Versão 11 — identificação de nacionalidade por histórico recente

Durante a carga, após consolidar as publicações do grupo, o sistema identifica os coautores externos e consulta as produções mais recentes de cada perfil bibliográfico. Por padrão são usadas as 10 publicações mais recentes de cada coautor, exclusivamente para estimar seu país principal. Essas publicações auxiliares não entram nos dashboards, tabelas, métricas, mapas, exportações ou grafo.

A instituição escolhida pelo usuário para autores do grupo continua tendo prioridade. Para coautores externos, a estimativa baseada no histórico recente tem prioridade sobre uma afiliação isolada observada em uma única coautoria do grupo. A quantidade de trabalhos recentes e a concorrência das consultas podem ser ajustadas na tela de configuração.
