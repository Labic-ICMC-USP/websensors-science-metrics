# WebSensors Science Metrics

O **WebSensors Science Metrics** integra o projeto de pesquisa **WebSensors**, que investiga métodos de Inteligência Artificial e Aprendizado de Máquina para transformar dados heterogêneos em informações estruturadas que possam apoiar análise, descoberta de conhecimento e tomada de decisão.

O projeto está organizado em três grandes frentes

* Sociedade
* Governo
* Ciência e Inovação

Em todas as frentes, os dados brutos passam por etapas de coleta, pré processamento, integração e enriquecimento para a construção de **grafos de conhecimento**.

Esses grafos representam entidades, eventos e relações identificados nas diferentes fontes de dados e permitem conectar informações originalmente distribuídas entre bases independentes.

Uma camada importante dessa representação utiliza a estrutura **5W1H** para descrever eventos.

```text
Who
Quem participou

What
O que aconteceu

When
Quando aconteceu

Where
Onde aconteceu

Why
Por que aconteceu

How
Como aconteceu
```

Essa representação permite organizar diferentes tipos de informação a partir de uma estrutura comum.

Uma notícia pode descrever um evento social.

Um documento governamental pode apresentar uma política pública ou uma ação planejada.

Uma publicação científica pode representar conhecimento, competências e resultados produzidos por uma comunidade de pesquisa.

A integração dessas informações em grafos de conhecimento permite construir uma visão conectada dos fenômenos analisados.

```text
SOCIEDADE
Eventos e demandas
        |
        v
Grafo de Conhecimento
        ^
        |
GOVERNO ---------------- CIÊNCIA E INOVAÇÃO
Políticas                  Competências
Programas                  Pesquisadores
Prioridades                Formação
                           Colaboração
```

A camada de conhecimento produzida pelo WebSensors pode ser utilizada por diferentes métodos analíticos e modelos computacionais.

Entre as possibilidades estão

* análise temporal de eventos
* modelagem de tópicos
* identificação de tendências
* análise de redes
* detecção de comunidades
* modelos preditivos
* identificação de relações entre eventos
* investigação de relações de causa e efeito
* descoberta de padrões
* recomendação
* recuperação de informação
* aprendizado em grafos
* modelos baseados em Large Language Models

Esses métodos podem ser associados a diferentes aplicações.

Uma demanda identificada na sociedade pode ser relacionada a uma política pública.

Uma política pública pode ser relacionada às competências científicas necessárias para sua execução.

Um problema observado em determinado território pode ser relacionado a pesquisadores, grupos, instituições e tecnologias capazes de contribuir com sua análise.

O objetivo do WebSensors é oferecer uma infraestrutura computacional para organizar essas diferentes fontes de evidência e permitir sua análise de forma integrada.

## Sociedade

A frente de **Sociedade** busca identificar e acompanhar fenômenos observados a partir de fontes como notícias, documentos, mídias digitais e outras fontes abertas.

Esses dados permitem identificar eventos, atores, localidades, períodos e relações relevantes para compreender problemas e demandas presentes na sociedade.

As informações coletadas são processadas e transformadas em entidades e eventos que podem ser integrados ao grafo de conhecimento do WebSensors.

Essa estrutura permite analisar a evolução dos fenômenos ao longo do tempo, sua distribuição territorial e suas relações com outros eventos e fontes de informação.

## Governo

A frente de **Governo** organiza informações relacionadas a políticas públicas, programas, planejamento, documentos oficiais, indicadores e bases administrativas.

Essa camada permite representar prioridades governamentais, problemas públicos, ações planejadas e instrumentos de política pública.

A integração com as demais frentes permite relacionar políticas e programas aos fenômenos observados na sociedade e às capacidades científicas existentes.

## Ciência e Inovação

A frente de **Ciência e Inovação** busca identificar capacidades científicas, tecnológicas e de formação de recursos humanos.

Pesquisadores, estudantes, programas de pós graduação, grupos de pesquisa, instituições, produção intelectual e redes de colaboração oferecem diferentes evidências sobre essas capacidades.

Essa frente permite investigar quais competências estão disponíveis para contribuir com demandas da sociedade, do governo e do setor produtivo.

Também permite analisar onde essas competências estão localizadas, como estão distribuídas entre instituições, como se organizam as redes de colaboração e onde ocorre a formação de novos recursos humanos.

O **WebSensors Science Metrics** é uma das plataformas desenvolvidas para essa frente.

# WebSensors Science Metrics

O **WebSensors Science Metrics** é uma plataforma para coleta, organização, enriquecimento e análise de informações relacionadas à atividade científica.

A plataforma permite analisar pesquisadores, grupos, programas e instituições a partir de sua produção intelectual e das relações presentes no ecossistema científico.

A partir de uma lista inicial de pesquisadores, o sistema recupera informações sobre

* produção científica
* coautores
* instituições
* países
* veículos de publicação
* tópicos de pesquisa
* citações
* impacto científico
* redes de colaboração

Essas informações são utilizadas para construir um grafo de conhecimento que representa progressivamente a estrutura científica do grupo analisado.

```text
Pesquisadores
      |
      v
Produção científica
      |
      v
Instituições e coautores
      |
      v
Resolução de entidades
      |
      v
Enriquecimento do grafo
      |
      v
Indicadores e redes de colaboração
```

## Fontes de dados científicos

A versão atual utiliza dados disponibilizados pelo **OpenAlex**.

O acesso pode ocorrer diretamente pela infraestrutura pública do OpenAlex ou por meio de um servidor local compatível com sua API.

Essa segunda possibilidade permite manter uma cópia local da base de dados e executar o serviço no próprio ambiente computacional da instituição.

A configuração do WebSensors Science Metrics permite definir o endpoint utilizado para as consultas.

Dessa forma, uma mesma pipeline pode trabalhar com

```text
OpenAlex público

ou

Servidor OpenAlex compatível executado localmente
```

O uso de uma infraestrutura local pode ser interessante em cenários com grandes volumes de consultas, necessidade de maior controle sobre os dados ou integração com outras bases institucionais.

O OpenAlex é utilizado como fonte de evidências.

Informações relacionadas à identidade de pesquisadores, instituições e países podem apresentar inconsistências ou ambiguidades.

Por esse motivo, o WebSensors Science Metrics mantém os dados originais e constrói novas entidades durante as etapas de processamento e enriquecimento.

## Cienciometria e análise de capacidades científicas

A cienciometria oferece instrumentos para analisar diferentes dimensões da atividade científica.

A produção intelectual permite observar a evolução da atividade de pesquisa.

As citações fornecem evidências sobre a circulação e o impacto dos resultados científicos.

As redes de colaboração ajudam a compreender como pesquisadores, grupos e instituições se conectam.

A análise dos tópicos permite acompanhar áreas de atuação e mudanças nos temas investigados.

As informações institucionais ajudam a compreender onde essas capacidades estão localizadas.

O WebSensors Science Metrics organiza essas diferentes dimensões em uma mesma infraestrutura de dados e conhecimento.

Uma aplicação importante é o mapeamento das capacidades científicas existentes em uma universidade, programa de pós graduação, grupo de pesquisa ou conjunto de instituições.

Essa análise pode apoiar a identificação de pesquisadores relacionados a determinado problema e a formação de equipes para projetos científicos, tecnológicos ou institucionais.

## Internacionalização da pesquisa

As redes internacionais de colaboração constituem uma dimensão importante da atividade científica.

O WebSensors Science Metrics busca identificar as relações entre pesquisadores brasileiros e pesquisadores vinculados principalmente a instituições de outros países.

Essa análise permite investigar

* quais grupos apresentam maior inserção internacional
* quais países mantêm colaboração com determinado grupo
* quais instituições estrangeiras aparecem com maior frequência
* quais pesquisadores atuam como principais conexões internacionais
* quais temas concentram maior colaboração internacional
* como a internacionalização evolui ao longo do tempo

A dimensão temática é particularmente relevante.

Uma rede de colaboração internacional pode ser analisada em conjunto com os temas das publicações para identificar áreas em que pesquisadores brasileiros possuem maior integração com comunidades científicas internacionais.

Também é possível identificar temas estratégicos em que a colaboração internacional ainda é limitada.

Essas informações podem apoiar ações de internacionalização, formação de redes de pesquisa, mobilidade acadêmica e planejamento institucional.

## Indicadores de impacto e FWCI

A comparação direta do número de citações entre diferentes áreas científicas apresenta limitações.

Cada comunidade possui seus próprios padrões de publicação e citação.

Por esse motivo, o WebSensors Science Metrics incorpora indicadores normalizados de impacto, com atenção especial ao **FWCI**.

O FWCI permite analisar o impacto de uma publicação considerando o comportamento esperado de citações para trabalhos comparáveis.

Essa característica torna o indicador especialmente útil para análises que envolvem pesquisadores ou grupos de diferentes áreas.

No WebSensors Science Metrics, o FWCI pode ser utilizado para analisar

* impacto médio da produção de um pesquisador
* impacto médio de um grupo
* evolução do impacto ao longo do tempo
* diferenças entre produção nacional e internacional
* impacto associado a diferentes temas
* comparação entre grupos científicos

Por exemplo, dois grupos podem atuar em áreas com padrões de citação bastante diferentes.

O número absoluto de citações pode favorecer naturalmente uma das áreas.

Indicadores normalizados permitem realizar uma comparação mais adequada entre esses grupos.

A combinação entre FWCI, produção científica, redes de colaboração e internacionalização oferece uma visão mais ampla das características de um grupo de pesquisa.

## Formação de recursos humanos

A capacidade científica de uma instituição também pode ser observada por sua atuação na formação de pesquisadores.

A integração futura com outras bases permitirá incorporar informações sobre

* iniciação científica
* mestrado
* doutorado
* pós doutorado
* orientação acadêmica
* projetos de pesquisa
* trajetória de egressos

Essa dimensão permitirá relacionar competências científicas existentes com as competências que estão sendo formadas.

Um programa de pós graduação poderá ser analisado a partir de sua produção científica, das redes de colaboração de seus pesquisadores e da formação de novos recursos humanos em diferentes temas.

## Mapeamento de competências científicas

A produção científica fornece diferentes evidências sobre as competências de pesquisadores e grupos.

Títulos, tópicos, resumos, conceitos, coautores e instituições podem ser utilizados para representar as áreas de atuação de uma comunidade científica.

O grafo de conhecimento permite conectar essas evidências.

```text
Pesquisador
    |
    +---- publicou ----> Trabalho
    |
    +---- vinculado ---> Instituição
    |
    +---- colaborou ----> Pesquisador
    |
    +---- atua em ------> Tema
```

Essa estrutura poderá ser conectada às outras frentes do WebSensors.

```text
Demanda da sociedade
        |
        v
Tema ou problema
        |
        v
Competência científica
        |
        v
Pesquisadores e grupos
        |
        v
Instituições e recursos humanos
```

Essa conexão permite investigar quais capacidades científicas podem contribuir com problemas identificados a partir de outras fontes.

# Pipeline

O WebSensors Science Metrics utiliza o **WebSensors Flow** para organizar sua pipeline de processamento.

O fluxo está dividido em quatro grandes etapas.

## 1. Ingestão de dados

A partir dos pesquisadores definidos no arquivo de configuração, o sistema consulta o OpenAlex ou um servidor local compatível.

Para cada nome são recuperados os candidatos mais prováveis.

Em seguida são coletadas informações sobre

* autores
* instituições
* trabalhos científicos
* autoria
* afiliações
* citações
* tópicos
* veículos de publicação
* indicadores científicos

Os dados são normalizados e armazenados no ArcadeDB.

Os principais tipos iniciais são

```text
authors
institutions
works
```

Os dados originais também são preservados para auditoria e novos processamentos.

## 2. Construção do grafo de conhecimento

Os dados coletados são utilizados para construir uma primeira versão do grafo.

Nessa etapa são representadas relações de autoria, afiliação, associação institucional, citação e associação entre pesquisadores informados e candidatos encontrados.

O resultado representa as evidências coletadas diretamente das fontes de dados.

## 3. Modeling e enriquecimento

A etapa de modeling melhora progressivamente a representação do grafo.

### 3.1 Resolução de identidade

O sistema busca identificar perfis que representam a mesma pessoa.

A resolução pode considerar evidências como

* nome
* ORCID
* produção científica
* DOI
* coautores
* instituições
* temas de pesquisa
* país

As evidências utilizadas são registradas no próprio grafo.

A partir desse processo são criadas entidades canônicas de pesquisadores.

### 3.2 Instituição principal

O sistema analisa o histórico das publicações e das afiliações associadas a cada pesquisador.

A instituição principal é estimada utilizando evidências como frequência, recência e persistência ao longo do tempo.

O resultado é armazenado como uma nova camada do grafo.

### 3.3 Enriquecimento dos coautores

Os coautores identificados na produção do grupo também passam por um processo de enriquecimento.

Para cada coautor, o sistema pode recuperar sua própria produção científica.

Essas publicações adicionais são utilizadas para obter uma visão mais ampla de sua trajetória e estimar sua instituição e seu país principal.

Os trabalhos utilizados nesse enriquecimento não são incorporados à produção intelectual do grupo analisado.

## 4. Reporting

A etapa final materializa informações para análise.

São produzidas tabelas com a produção intelectual e os principais indicadores do grupo.

Também é construído um grafo de colaboração utilizando as entidades resolvidas durante as etapas anteriores.

Entre os resultados disponíveis estão

* produção intelectual
* citações
* FWCI
* acesso aberto
* tópicos
* pesquisadores
* instituições
* países
* colaboração nacional
* colaboração internacional
* redes de coautoria

# Arquitetura

```text
OpenAlex
ou
Servidor local compatível
        |
        v
Ingestão
        |
        v
Dados normalizados
        |
        v
Knowledge Graph
        |
        v
Resolução de pesquisadores
        |
        v
Identificação de instituições
        |
        v
Enriquecimento de coautores
        |
        v
Knowledge Graph enriquecido
        |
        +----------> Indicadores
        |
        +----------> Produção intelectual
        |
        +----------> Internacionalização
        |
        +----------> Grafo de colaboração
```

O **WebSensors Flow** organiza e executa as etapas da pipeline.

O **ArcadeDB** armazena os dados e o grafo de conhecimento.

O **MLflow** registra execuções, parâmetros, métricas e artefatos produzidos durante o processamento.

# Integração com o WebSensors

O WebSensors Science Metrics contribui com a camada de Ciência e Inovação do projeto WebSensors.

A estrutura poderá ser integrada progressivamente a outras fontes.

Entre elas estão

* Currículo Lattes
* bases do CNPq
* Diretório dos Grupos de Pesquisa
* Plataforma Sucupira
* dados de programas de pós graduação
* informações sobre orientações
* projetos de pesquisa
* teses e dissertações
* patentes
* dados de inovação

Essa integração permitirá ampliar o grafo de conhecimento com informações sobre competências, formação de recursos humanos e capacidades institucionais.

As informações poderão também ser conectadas aos grafos produzidos pelas frentes de Sociedade e Governo.

```text
SOCIEDADE
Demandas
Eventos
Problemas
        |
        v
GRAFO DE CONHECIMENTO INTEGRADO
        ^
        |
GOVERNO ---------------- CIÊNCIA E INOVAÇÃO
Políticas                  Pesquisadores
Programas                  Competências
Prioridades                Formação
                           Colaboração
```

Essa infraestrutura poderá apoiar o mapeamento de pesquisadores para demandas específicas, a formação de equipes, a identificação de parceiros, a análise de internacionalização e o planejamento da formação de recursos humanos.

# Evolução do projeto

A versão atual prioriza métodos auditáveis para resolução de entidades e enriquecimento do grafo.

As próximas etapas de pesquisa incluem

* integração com novas bases científicas e acadêmicas
* uso de embeddings para representação semântica
* modelos de aprendizado de máquina para resolução de entidades
* identificação automática de competências
* modelagem de tópicos
* análise temporal
* aprendizado em grafos
* predição de relações
* identificação de comunidades científicas
* modelos preditivos
* Large Language Models para enriquecimento do grafo
* integração entre demandas e competências científicas

A estrutura baseada em grafos permite incorporar novas fontes e novos modelos progressivamente.

# Instalação e execução

As instruções completas para instalação, configuração e execução estão disponíveis em

```text
Tutorial-PT-BR.md
```

O tutorial apresenta a instalação e o teste do ArcadeDB, a configuração do MLflow, a execução da pipeline e a análise dos resultados.

# Projeto WebSensors

Site do projeto

https://websensors.icmc.usp.br/

