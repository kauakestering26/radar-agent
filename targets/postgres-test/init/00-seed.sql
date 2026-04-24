-- Seed do PostgreSQL de teste — dispara TODAS as heurísticas do conector.
-- É esperado que um scan `postgresql` ache 20+ assets neste banco.
--
-- ORDEM: extensão → schemas → tabelas → INSERTs → índices (IVFFLAT exige dados).

-- Se um comando falhar, continua — prefere ver warnings a abortar o arquivo inteiro.
\set ON_ERROR_STOP off

-- ── 1. Extensão pgvector (heurística: vector_extension) ─────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 2. Schemas de stack ML (heurística: ml_schema) ──────────────────────────
CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS mlflow;
CREATE SCHEMA IF NOT EXISTS feast;
CREATE SCHEMA IF NOT EXISTS feature_store;

-- ── 3. Tabelas com colunas vector(N) em várias dimensões ─────────────────────
--     (heurística: embedding_store, com inferência de provedor pelo N)

-- vector(1536) — OpenAI text-embedding-ada-002 / 3-small (default)
CREATE TABLE IF NOT EXISTS public.document_embeddings (
    id           SERIAL PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    content      TEXT,
    embedding    vector(1536)
);

-- vector(3072) — OpenAI text-embedding-3-large
CREATE TABLE IF NOT EXISTS ml.knowledge_chunks (
    id           SERIAL PRIMARY KEY,
    chunk_text   TEXT,
    vec          vector(3072)
);

-- vector(768) — sentence-transformers / BERT / text-embedding-3-small reduzido
CREATE TABLE IF NOT EXISTS public.product_vectors (
    id          SERIAL PRIMARY KEY,
    product_id  TEXT,
    vec         vector(768)
);

-- ── 4. Tabelas do MLflow tracking server (heurística: model_registry) ───────
CREATE TABLE IF NOT EXISTS mlflow.experiments (
    experiment_id BIGSERIAL PRIMARY KEY,
    name          TEXT UNIQUE,
    artifact_location TEXT
);
CREATE TABLE IF NOT EXISTS mlflow.runs (
    run_uuid     TEXT PRIMARY KEY,
    experiment_id BIGINT REFERENCES mlflow.experiments(experiment_id),
    status       TEXT
);
CREATE TABLE IF NOT EXISTS mlflow.metrics (
    key      TEXT, value DOUBLE PRECISION,
    run_uuid TEXT REFERENCES mlflow.runs(run_uuid)
);
CREATE TABLE IF NOT EXISTS mlflow.params (
    key      TEXT, value TEXT,
    run_uuid TEXT REFERENCES mlflow.runs(run_uuid)
);
CREATE TABLE IF NOT EXISTS mlflow.tags (
    key      TEXT, value TEXT,
    run_uuid TEXT REFERENCES mlflow.runs(run_uuid)
);
CREATE TABLE IF NOT EXISTS mlflow.registered_models (
    name         TEXT PRIMARY KEY,
    description  TEXT
);

-- ── 5. Tabelas com nomes suspeitos (heurística: ai_table_candidate) ─────────
CREATE TABLE IF NOT EXISTS public.prompts_log (
    id         SERIAL PRIMARY KEY,
    user_id    INT,
    prompt     TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.ml_predictions (
    id               BIGSERIAL PRIMARY KEY,
    model_name       TEXT,
    model_version    TEXT,
    framework        TEXT,
    input            JSONB,
    prediction       JSONB,
    confidence_score NUMERIC,
    accuracy         NUMERIC,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feature_store.user_features (
    user_id       BIGINT PRIMARY KEY,
    features      JSONB,
    feature_value TEXT,
    artifact_path TEXT
);

-- ── 6. Tabela de uso de LLM (colunas token_* etc.) ──────────────────────────
CREATE TABLE IF NOT EXISTS public.llm_usage (
    id            BIGSERIAL PRIMARY KEY,
    request_id    TEXT,
    tokens_input  INT,
    tokens_output INT,
    tokens_used   INT,
    completion    TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- ── 7. INSERTs PRIMEIRO (IVFFLAT precisa de dados antes do CREATE INDEX) ────
INSERT INTO public.document_embeddings (doc_id, content)
     VALUES ('doc-1', 'hello world'),
            ('doc-2', 'radar agent poc')
     ON CONFLICT DO NOTHING;

INSERT INTO ml.knowledge_chunks (chunk_text)
     VALUES ('sample chunk 1'), ('sample chunk 2')
     ON CONFLICT DO NOTHING;

INSERT INTO public.product_vectors (product_id)
     VALUES ('sku-001'), ('sku-002'), ('sku-003')
     ON CONFLICT DO NOTHING;

INSERT INTO mlflow.experiments (name) VALUES ('default') ON CONFLICT DO NOTHING;

-- ── 8. ÍNDICES VETORIAIS (heurística: vector_index) ─────────────────────────
-- ATENÇÃO: pgvector limita HNSW e IVFFLAT a 2000 dimensões pro tipo `vector`.
-- Embeddings maiores (ex: OpenAI text-embedding-3-large = 3072) precisam do
-- tipo `halfvec` (até 4000 dims com HNSW) ou ficam sem índice (busca linear).
-- Esta última situação é comum em produção e um ótimo sinal a reportar.

-- HNSW em vector(1536) — dentro do limite, funciona.
CREATE INDEX IF NOT EXISTS document_embeddings_hnsw
    ON public.document_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- IVFFLAT em vector(768) — também dentro do limite. lists=1 é mínimo;
-- em produção usaria sqrt(N) como referência.
CREATE INDEX IF NOT EXISTS product_vectors_ivfflat
    ON public.product_vectors
    USING ivfflat (vec vector_l2_ops) WITH (lists = 1);

-- `ml.knowledge_chunks.vec` é vector(3072) — passa do limite. Tabela
-- intencionalmente SEM índice pra simular cenário real de cliente usando
-- OpenAI text-embedding-3-large sem migrar pra halfvec.

-- ── 9. ANALYZE pra atualizar reltuples (usado quando sample_rows=true) ──────
ANALYZE public.document_embeddings;
ANALYZE ml.knowledge_chunks;
ANALYZE public.product_vectors;
ANALYZE mlflow.experiments;
