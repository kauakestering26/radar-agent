"""
PostgreSQL Connector — descobre assets de IA via API nativa do Postgres.

O diferencial do Radar AI vs. concorrentes de network monitoring
(Alltrue/Varonis Atlas) mora aqui: em vez de inferir de fora pelo tráfego,
o agent consulta `information_schema`, `pg_catalog` e extensões diretamente
— enxerga metadados ricos (schemas, tipos, índices, extensões) que proxy
de rede jamais alcança.

Heurísticas atuais:
  1. Extensão `pgvector` instalada
  2. Extensão `pgml` (PostgresML — modelos treinados in-database)
  3. Colunas do tipo `vector(N)` — com inferência do provedor pelo N
  4. Índices vetoriais HNSW / IVFFLAT
  5. Schemas ML-related (mlflow, feast, kubeflow, dbt_*)
  6. Tabelas do tracking server do MLflow
  7. Nomes de tabela suspeitos (embeddings, features, predictions, prompts…)
  8. Colunas com nomes de payload de IA (prompt, completion, embedding…)

Credenciais:
  Lidas de env vars no ambiente do agent. NUNCA chegam via WebSocket.
  - POSTGRES_DSN=postgresql://user:pass@host:5432/db
  ou
  - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

Config opcional (passado via task do control plane, sem credencial):
  {
    "schemas": ["public", "ml"],   # restringe a N schemas (default: todos não-system)
    "sample_rows": false            # se true, inclui contagem aproximada de linhas
  }
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import asyncpg

log = logging.getLogger(__name__)


# ── Mapa de dimensões conhecidas → provedor provável ────────────────────────
# Usado pra enriquecer o `detail` de colunas vector(N) com pistas de origem.
EMBEDDING_DIM_HINTS: dict[int, str] = {
    384:  "sentence-transformers/all-MiniLM-L6-v2 (ou similar)",
    512:  "CLIP image/text ou distilbert",
    768:  "BERT base, sentence-transformers/all-mpnet-base-v2 ou OpenAI text-embedding-3-small (reduzido)",
    1024: "Cohere embed-v3, Voyage AI ou BERT large",
    1536: "OpenAI text-embedding-ada-002 ou text-embedding-3-small (default)",
    3072: "OpenAI text-embedding-3-large",
    4096: "LLaMA-2 hidden state",
}

# Schemas do sistema que devem ser ignorados por default.
SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}

# Regex-ish patterns por heurística textual — usamos ILIKE com ANY(ARRAY[...])
SUSPICIOUS_TABLE_PATTERNS = [
    "%embedding%", "%embeddings%", "%vector%", "%vectors%",
    "%feature_store%", "%features%",
    "%prediction%", "%predictions%", "%inference%", "%inferences%",
    "%prompt%", "%prompts%", "%completion%", "%completions%",
    "%training_data%", "%train_set%", "%dataset%", "%datasets%",
    "%model_registry%", "%model_versions%",
]

SUSPICIOUS_COLUMN_PATTERNS = [
    "prompt", "completion", "embedding", "embeddings",
    "prediction", "predictions", "confidence_score",
    "model_version", "model_name", "inference_result",
    "tokens_input", "tokens_output", "tokens_used",
]

# Schemas cujo NOME denota stack de ML
ML_SCHEMA_PATTERNS = [
    "ml", "ml_%", "mlflow", "feast", "kubeflow",
    "feature_store", "feature_%", "airflow",
]

# Tabelas clássicas do MLflow tracking server
MLFLOW_SIGNATURE_TABLES = {"experiments", "runs", "metrics", "params", "tags", "registered_models"}


# ── Entrypoint ─────────────────────────────────────────────────────────────

async def scan(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Contrato público chamado por agent/main.py."""
    dsn = _resolve_dsn()
    if not dsn:
        raise RuntimeError(
            "Credenciais do PostgreSQL não configuradas no agent. "
            "Defina POSTGRES_DSN (ou POSTGRES_HOST/PORT/DB/USER/PASSWORD) "
            "nas env vars do agent."
        )

    schemas_filter: list[str] | None = config.get("schemas")
    include_row_counts: bool = bool(config.get("sample_rows", False))

    log.info("PostgreSQL: conectando (schemas=%s, sample_rows=%s)", schemas_filter, include_row_counts)

    conn = await asyncpg.connect(dsn=dsn, timeout=15)
    try:
        server_version = await conn.fetchval("SHOW server_version")
        log.info("PostgreSQL: conectado (server_version=%s)", server_version)

        assets: list[dict[str, Any]] = []
        now = datetime.utcnow().isoformat()

        # Ordem importa só por log; cada heurística é independente.
        assets += await _detect_ai_extensions(conn)
        assets += await _detect_vector_columns(conn, schemas_filter, include_row_counts)
        assets += await _detect_vector_indexes(conn, schemas_filter)
        assets += await _detect_ml_schemas(conn)
        assets += await _detect_mlflow_tracking(conn)
        assets += await _detect_suspicious_tables(conn, schemas_filter)
        assets += await _detect_suspicious_columns(conn, schemas_filter)

        # Enriquecimento comum a todos os assets deste scan
        for a in assets:
            a.setdefault("connector", "postgresql")
            a.setdefault("discovered_at", now)
            a.setdefault("source", {
                "database": _redact(dsn).get("database"),
                "server_version": server_version,
            })

        log.info("PostgreSQL: scan concluído — %d assets", len(assets))
        return assets

    finally:
        await conn.close()


# ── Heurísticas ────────────────────────────────────────────────────────────

async def _detect_ai_extensions(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    """pgvector, pgml e outras extensões que sinalizam stack de IA."""
    rows = await conn.fetch("""
        SELECT extname, extversion
        FROM pg_extension
        WHERE extname IN ('vector', 'pgml', 'pgvectorscale', 'lantern', 'pgrouting_plpython')
    """)

    assets = []
    for r in rows:
        ext, ver = r["extname"], r["extversion"]
        if ext == "vector":
            assets.append({
                "type": "vector_extension",
                "name": f"pgvector v{ver}",
                "detail": f"Extensão pgvector habilitada (v{ver}) — habilita armazenamento e busca vetorial nativa.",
                "confidence": 0.99,
                "severity": "high",
                "evidence": {"extension": ext, "version": ver},
            })
        elif ext == "pgml":
            assets.append({
                "type": "in_database_ml",
                "name": f"PostgresML v{ver}",
                "detail": f"Extensão pgml v{ver} instalada — treina e serve modelos ML dentro do próprio Postgres (risco elevado: modelos e dados coexistem).",
                "confidence": 0.99,
                "severity": "high",
                "evidence": {"extension": ext, "version": ver},
            })
        else:
            assets.append({
                "type": "ai_extension",
                "name": f"{ext} v{ver}",
                "detail": f"Extensão '{ext}' relacionada a IA/ML detectada.",
                "confidence": 0.9,
                "severity": "medium",
                "evidence": {"extension": ext, "version": ver},
            })
    return assets


async def _detect_vector_columns(
    conn: asyncpg.Connection,
    schemas_filter: list[str] | None,
    include_row_counts: bool,
) -> list[dict[str, Any]]:
    """
    Colunas do tipo `vector(N)` — sinal mais forte de embedding store.
    A dimensão N dá pistas do provedor (1536 = OpenAI ada, 3072 = text-embedding-3-large, etc.).
    """
    # atttypid do tipo vector é dinâmico (extensão). Usamos o nome formatado.
    # IMPORTANTE: pg_attribute também tem linhas pra ÍNDICES e outros relkinds
    # (materialized views, foreign tables, etc.). Filtrar por relkind é crítico
    # pra não reportar um índice HNSW como se fosse uma tabela embedding.
    #   'r' = tabela regular
    #   'p' = tabela particionada
    #   'f' = foreign table (tipicamente Feast, dbt sources)
    rows = await conn.fetch("""
        SELECT
            n.nspname                                       AS schema_name,
            c.relname                                       AS table_name,
            a.attname                                       AS column_name,
            format_type(a.atttypid, a.atttypmod)            AS full_type,
            a.atttypmod                                     AS typmod
        FROM pg_attribute a
        JOIN pg_class      c ON c.oid = a.attrelid
        JOIN pg_namespace  n ON n.oid = c.relnamespace
        JOIN pg_type       t ON t.oid = a.atttypid
        WHERE t.typname = 'vector'
          AND c.relkind IN ('r', 'p', 'f')
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND n.nspname <> ALL($1::text[])
          AND ($2::text[] IS NULL OR n.nspname = ANY($2::text[]))
    """, list(SYSTEM_SCHEMAS), schemas_filter)

    assets = []
    for r in rows:
        schema, table, column, full_type = r["schema_name"], r["table_name"], r["column_name"], r["full_type"]
        dim = _extract_vector_dim(full_type)
        hint = EMBEDDING_DIM_HINTS.get(dim) if dim else None
        qualified = f"{schema}.{table}.{column}"

        row_count_note = ""
        if include_row_counts:
            try:
                approx = await conn.fetchval(
                    "SELECT reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=$1 AND c.relname=$2",
                    schema, table,
                )
                if approx and approx > 0:
                    row_count_note = f" (~{approx:,} linhas aproximadas)"
            except Exception as e:  # pragma: no cover
                log.debug("reltuples falhou pra %s.%s: %s", schema, table, e)

        detail = f"Coluna `{qualified}` do tipo `{full_type}`{row_count_note}."
        if hint:
            detail += f" Dimensão {dim} compatível com {hint}."

        assets.append({
            "type": "embedding_store",
            "name": f"{qualified} ({full_type})",
            "detail": detail,
            "confidence": 0.97,
            "severity": "high",
            "location": qualified,
            "evidence": {
                "schema": schema, "table": table, "column": column,
                "type": full_type, "dimension": dim,
                "provider_hint": hint,
            },
        })
    return assets


async def _detect_vector_indexes(
    conn: asyncpg.Connection,
    schemas_filter: list[str] | None,
) -> list[dict[str, Any]]:
    """Índices HNSW/IVFFLAT — confirmação forte de busca vetorial em produção."""
    rows = await conn.fetch("""
        SELECT
            schemaname, tablename, indexname, indexdef
        FROM pg_indexes
        WHERE (indexdef ILIKE '%USING hnsw%'
            OR indexdef ILIKE '%USING ivfflat%'
            OR indexdef ILIKE '%USING diskann%')
          AND schemaname <> ALL($1::text[])
          AND ($2::text[] IS NULL OR schemaname = ANY($2::text[]))
    """, list(SYSTEM_SCHEMAS), schemas_filter)

    assets = []
    for r in rows:
        method = "hnsw" if "hnsw" in r["indexdef"].lower() else \
                 "ivfflat" if "ivfflat" in r["indexdef"].lower() else "diskann"
        qualified = f"{r['schemaname']}.{r['tablename']}"
        assets.append({
            "type": "vector_index",
            "name": f"{r['indexname']} ({method.upper()}) em {qualified}",
            "detail": f"Índice vetorial `{method}` — indica busca semântica em produção.",
            "confidence": 0.99,
            "severity": "high",
            "location": f"{qualified}#{r['indexname']}",
            "evidence": {
                "schema": r["schemaname"], "table": r["tablename"],
                "index_name": r["indexname"], "method": method,
                "definition": r["indexdef"],
            },
        })
    return assets


async def _detect_ml_schemas(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    """Schemas com nomes de stack ML."""
    rows = await conn.fetch("""
        SELECT nspname
        FROM pg_namespace
        WHERE nspname ILIKE ANY($1::text[])
          AND nspname <> ALL($2::text[])
    """, ML_SCHEMA_PATTERNS, list(SYSTEM_SCHEMAS))

    return [{
        "type": "ml_schema",
        "name": f"Schema `{r['nspname']}`",
        "detail": f"Schema com nome compatível com stack ML/IA (`{r['nspname']}`).",
        "confidence": 0.78,
        "severity": "medium",
        "location": r["nspname"],
        "evidence": {"schema": r["nspname"]},
    } for r in rows]


async def _detect_mlflow_tracking(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    """
    MLflow tracking server grava em tabelas específicas. Se todas (ou quase)
    estiverem no mesmo schema, é MLflow com alta confidence.
    """
    rows = await conn.fetch("""
        SELECT table_schema, array_agg(table_name ORDER BY table_name) AS tables
        FROM information_schema.tables
        WHERE table_name = ANY($1::text[])
          AND table_schema <> ALL($2::text[])
        GROUP BY table_schema
    """, list(MLFLOW_SIGNATURE_TABLES), list(SYSTEM_SCHEMAS))

    assets = []
    for r in rows:
        found = set(r["tables"])
        overlap = len(found & MLFLOW_SIGNATURE_TABLES)
        if overlap < 3:
            continue  # coincidência, não MLflow
        assets.append({
            "type": "model_registry",
            "name": f"MLflow tracking server (schema `{r['table_schema']}`)",
            "detail": f"Tabelas de assinatura do MLflow detectadas ({overlap}/{len(MLFLOW_SIGNATURE_TABLES)}): {sorted(found)}.",
            "confidence": 0.95 if overlap >= 5 else 0.85,
            "severity": "high",
            "location": r["table_schema"],
            "evidence": {"schema": r["table_schema"], "signature_tables": sorted(found)},
        })
    return assets


async def _detect_suspicious_tables(
    conn: asyncpg.Connection,
    schemas_filter: list[str] | None,
) -> list[dict[str, Any]]:
    """Nomes de tabela que soam como IA/ML, mesmo sem tipos vetoriais."""
    rows = await conn.fetch("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_name ILIKE ANY($1::text[])
          AND table_schema <> ALL($2::text[])
          AND ($3::text[] IS NULL OR table_schema = ANY($3::text[]))
    """, SUSPICIOUS_TABLE_PATTERNS, list(SYSTEM_SCHEMAS), schemas_filter)

    return [{
        "type": "ai_table_candidate",
        "name": f"{r['table_schema']}.{r['table_name']}",
        "detail": f"Nome de tabela sugere payload de IA/ML. Requer validação manual.",
        "confidence": 0.72,
        "severity": "low",
        "location": f"{r['table_schema']}.{r['table_name']}",
        "evidence": {"schema": r["table_schema"], "table": r["table_name"]},
    } for r in rows]


async def _detect_suspicious_columns(
    conn: asyncpg.Connection,
    schemas_filter: list[str] | None,
) -> list[dict[str, Any]]:
    """Nomes de coluna que denunciam payload de LLM/embedding."""
    rows = await conn.fetch("""
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE column_name = ANY($1::text[])
          AND table_schema <> ALL($2::text[])
          AND ($3::text[] IS NULL OR table_schema = ANY($3::text[]))
    """, SUSPICIOUS_COLUMN_PATTERNS, list(SYSTEM_SCHEMAS), schemas_filter)

    return [{
        "type": "ai_column_candidate",
        "name": f"{r['table_schema']}.{r['table_name']}.{r['column_name']}",
        "detail": f"Coluna `{r['column_name']}` ({r['data_type']}) sugere armazenamento de payload de IA.",
        "confidence": 0.70,
        "severity": "low",
        "location": f"{r['table_schema']}.{r['table_name']}.{r['column_name']}",
        "evidence": {
            "schema": r["table_schema"], "table": r["table_name"],
            "column": r["column_name"], "data_type": r["data_type"],
        },
    } for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────────

def _resolve_dsn() -> str | None:
    """DSN explícita ganha; senão monta a partir dos campos discretos."""
    dsn = os.getenv("POSTGRES_DSN")
    if dsn:
        return dsn

    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "postgres")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD", "")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def _extract_vector_dim(full_type: str) -> int | None:
    """`vector(1536)` → 1536; `vector` → None."""
    if "(" in full_type and ")" in full_type:
        inside = full_type[full_type.find("(") + 1 : full_type.rfind(")")]
        try:
            return int(inside)
        except ValueError:
            return None
    return None


def _redact(dsn: str) -> dict[str, str | None]:
    """Extrai só o que é seguro mostrar no payload enviado ao cloud (sem senha)."""
    try:
        # asyncpg expõe um parser, mas não queremos importar urllib aqui por enquanto;
        # string simples é suficiente pra extrair database.
        tail = dsn.rsplit("/", 1)[-1]
        db = tail.split("?", 1)[0] or None
        return {"database": db}
    except Exception:
        return {"database": None}
