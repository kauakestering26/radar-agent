# Paridade de Discovery — Agent vs. Radar Cloud (PostgreSQL)

> Comparativo das heurísticas aplicadas hoje pelo Radar Cloud em produção
> contra as implementadas no `agent-poc`. Objetivo: garantir que o POC não
> regride em capacidade de descoberta antes de validar com cliente.

## Arquiteturas são complementares, não sobrepostas

**Radar Cloud (hoje):** scanner genérico puxa DDL como texto → passa pra um
detector de patterns textuais. A mesma engine serve Postgres, MySQL, SQL
Server, MongoDB, Oracle, Redis. Ganho: abrangência. Custo: perde metadado
rico específico de cada banco.

**Agent (POC):** conector especializado consulta API nativa
(`pg_catalog`, `information_schema`, `pg_extension`) com queries direcionadas.
Ganho: metadados que só o Postgres sabe (extensões, dimensão do vector, método
de índice). Custo: código específico por tipo de banco.

Operacionalmente, é o mesmo dilema IICS vs. proxy de rede: quem fala a língua
nativa enxerga coisas que o generalista não vê.

## Matriz de paridade

| # | Capacidade | Radar Cloud | Agent-POC | Observação |
| - | ---------- | :---------: | :-------: | ---------- |
| 1 | Pattern textual em nome de tabela (`embeddings`, `features`, `model_registry`...) | ✅ 13 patterns | ⚠️ 6 patterns | Gap: agent não cobre `feature_groups`, `feature_definitions`, `model_metadata`, `data_lineage`, `datasets`, `experiments` individual |
| 2 | Pattern textual em nome de coluna (`model_name`, `framework`, `accuracy`...) | ✅ 11 patterns | ⚠️ 8 patterns | Gap: agent não cobre `model_name`, `framework`, `accuracy`, `precision`, `recall`, `feature_value`, `artifact_path` |
| 3 | Extensão pgvector instalada | ❌ | ✅ | Agent-only — só detectável via `pg_extension` |
| 4 | Extensão pgml (PostgresML) | ❌ | ✅ | Agent-only — modelo ML in-database é sinal forte |
| 5 | Tipo `vector(N)` com dimensão exata | ❌ (detecta a palavra "vector" no DDL) | ✅ (detecta tipo + infere provedor por N) | Agent sabe que 1536 = OpenAI ada, 3072 = 3-large, etc. |
| 6 | Índices HNSW / IVFFLAT / DiskANN | ❌ | ✅ | Agent-only — confirmação forte de busca vetorial em prod |
| 7 | MLflow tracking server por assinatura de tabelas | ❌ (tem pattern "experiments" isolado) | ✅ (3+ tabelas da signature) | Correlação cruzada só no agent |
| 8 | Schemas ML-related pelo nome (`mlflow`, `feast`, `kubeflow`) | ❌ | ✅ | |
| 9 | Escaneia múltiplos schemas | ❌ **só `public`** | ✅ (todos não-system, filtrável) | **Crítico.** Radar cloud perde tudo fora de `public`. |
| 10 | Categoria (weak/medium/strong/confirmatory) | ✅ | ❌ (só confidence numérica) | Gap do agent — precisa mapear pra taxonomia do Radar |
| 11 | Asset type taxonomia (ai_service/agent/rag_pipeline/workflow/etc.) | ✅ | ⚠️ (taxonomia própria) | Gap do agent — precisa mapear pra downstream do Radar |
| 12 | DDL rico (colunas + tipos + nullable) | ✅ | ⚠️ (acesso via pg_attribute, mas não consolidado) | Agent pode extrair, hoje não consolida |

## Leitura rápida

- **O agent tem 5 capacidades que o Radar cloud não tem hoje** — todas vêm de
  acesso direto a metadados do Postgres. São o diferencial vs. Alltrue e
  também vs. o próprio Radar cloud atual.
- **O Radar cloud tem 3 capacidades que o agent não tem hoje** — todas são
  patterns textuais adicionais (mais nomes de tabela/coluna) e taxonomia.
  Custo de fechar: ~50 linhas de dicionário.
- **Há 1 gap crítico no Radar cloud que o agent já resolve**: o cloud só
  olha schema `public`. Clientes com MLflow em schema próprio (padrão da
  ferramenta) **não são detectados hoje**. O agent corrige isso.

## Gaps a fechar no agent antes do POC ser "comparável ao Radar cloud"

Ordem de esforço crescente:

1. **[15 min] Importar as duas dicts de patterns textuais do `detector.py`** para o
   conector do agent (`DATABASE_TABLE_PATTERNS` e `DATABASE_FIELD_PATTERNS`).
   Evita duplicar manutenção — idealmente vira módulo compartilhado.
2. **[15 min] Adicionar campo `category`** (weak/medium/strong/confirmatory) em todos
   os assets do agent, alinhando com a taxonomia do Radar cloud.
3. **[15 min] Adicionar campo `asset_type`** compatível com o Radar cloud
   (`ai_service` | `agent` | `rag_pipeline` | `workflow` | `unknown_ai`).
4. **[opcional, 30 min] Consolidar DDL rico** — montar o mesmo formato que
   `get_postgresql_table_ddl` retorna, pra que o Radar cloud consiga
   reprocessar o payload do agent com sua engine de detector existente sem
   mudança alguma no cloud. **Essa é a integração mais elegante**: agent vira
   um "scanner substituto" plug-and-play, e a engine do Radar continua igual.

## Ganhos que o agent já traz hoje (não regressão, upgrade)

1. **Cobertura de schemas** — resolve gap crítico do Radar cloud (só `public`)
2. **Detecção de extensões** — pgvector, pgml (invisível ao cloud)
3. **Métodos de índice vetorial** — HNSW/IVFFLAT (sinal mais confiável que nome)
4. **Inferência de provedor por dimensão** — narra a história do cliente: "você
   está usando OpenAI ada-002 em produção neste cluster"
5. **Detecção cruzada** — MLflow por assinatura, não só por nome isolado

## Conclusão pra decisão de negócio

Do ponto de vista de discovery, o agent **não regride** em PostgreSQL —
adiciona 5 capacidades novas e fecha 1 gap crítico. As 3 capacidades
textuais que faltam são trivialmente portáveis (~45 min de trabalho) e
idealmente compartilhadas num módulo de patterns comum.

Conclusão: a adoção do modelo agent não custa nada em capacidade de
descoberta e ganha bastante. O custo real está em onboarding (o cliente
tem que instalar algo) e em manutenção do binário do agent.
