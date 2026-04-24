# Segurança do Radar Agent

> Este documento existe pra responder objetivamente a pergunta que todo CISO
> faz em due diligence: **"o que exatamente vocês veem da minha infraestrutura?"**

## Princípio central

Credenciais dos seus sistemas (bancos, clusters, provedores de IA) **vivem
apenas na máquina onde você instala o agent**. O canal agent ↔ Radar Cloud é
um WebSocket *outbound-only* que carrega exclusivamente metadados sobre
ativos de IA descobertos. Nenhuma credencial trafega nesse canal.

Você pode provar isso empiricamente com o script incluso em
`tests/security/verify_no_credential_leak.py` — ele captura cada frame WS
num ciclo completo de scan e busca por fragmentos de credencial.

## Fluxo de dados (do ponto de vista do cliente)

```
SEU AMBIENTE (on-prem, VPC, air-gapped)        RADAR CLOUD
┌─────────────────────────────────────┐        ┌─────────────────────┐
│                                     │        │                     │
│  ┌────────────────────────────┐     │        │                     │
│  │  Credencial PostgreSQL     │     │        │                     │
│  │  (em env var ou vault)     │     │        │                     │
│  └──────────────┬─────────────┘     │        │                     │
│                 │ usada localmente  │        │                     │
│                 ▼                   │        │                     │
│  ┌────────────────────────────┐     │   WS   │ ┌─────────────────┐ │
│  │  Radar Agent               │────────────────▶│ Control Plane   │ │
│  │  - Conecta no Postgres     │     │outbound│ │ - recebe assets │ │
│  │  - Consulta metadados      │     │ only   │ │   descobertos   │ │
│  │  - Envia SÓ assets         │     │        │ │ - nunca vê DSN  │ │
│  └────────────────────────────┘     │        │ └─────────────────┘ │
│                                     │        │                     │
└─────────────────────────────────────┘        └─────────────────────┘
```

## Tipos de mensagem no WebSocket

O protocolo tem 4 tipos. Exemplos reais (capturados pelo script de verificação):

### 1. `welcome` — cloud → agent

Enviada uma vez quando o agent conecta.

```json
{
  "type": "welcome",
  "agent_id": "agent-cliente-1",
  "message": "Conectado ao Radar Control Plane"
}
```

Nenhum campo sensível.

### 2. `heartbeat` — agent → cloud (cada N segundos)

```json
{
  "type": "heartbeat",
  "agent_id": "agent-cliente-1"
}
```

Nenhum campo sensível. O cloud responde com `heartbeat_ack` (também vazio).

### 3. `scan_task` — cloud → agent

Disparada quando o usuário aciona um scan pela UI/API do Radar Cloud.

```json
{
  "type": "scan_task",
  "scan_id": "dccad4cc",
  "connector": "postgresql",
  "config": {
    "schemas": ["public", "ml"],
    "sample_rows": false
  }
}
```

**Nunca contém credenciais.** O `connector` é apenas o nome do conector a
usar (o agent resolve a credencial localmente, via env var). O `config` é
opcional e só carrega filtros inócuos (schemas a incluir, flags).

### 4. `scan_result` — agent → cloud

Payload principal. Contém os ativos de IA descobertos. Exemplo resumido:

```json
{
  "type": "scan_result",
  "scan_id": "dccad4cc",
  "connector": "postgresql",
  "assets": [
    {
      "type": "vector_extension",
      "name": "pgvector v0.8.2",
      "detail": "Extensão pgvector habilitada (v0.8.2)...",
      "confidence": 0.99,
      "severity": "high",
      "evidence": {"extension": "vector", "version": "0.8.2"},
      "source": {"database": "radar_test", "server_version": "16.13"}
    },
    {
      "type": "embedding_store",
      "name": "public.document_embeddings.embedding (vector(1536))",
      "location": "public.document_embeddings.embedding",
      "evidence": {
        "schema": "public",
        "table": "document_embeddings",
        "column": "embedding",
        "type": "vector(1536)",
        "dimension": 1536,
        "provider_hint": "OpenAI text-embedding-ada-002..."
      }
    }
  ]
}
```

**O que aparece aqui**: nomes de schema/tabela/coluna, tipo de coluna, versão
do servidor, nome do banco (não user/host/senha). Dimensão do vector (útil
pra inferir o provedor do embedding).

**O que NÃO aparece**: nenhum campo da DSN — host, port, user, password,
string de conexão completa. Nenhuma linha de dado do cliente (o conector
lê só metadados de `pg_catalog` e `information_schema`).

## O que o conector PostgreSQL lê (queries SQL em claro)

Todas as queries são read-only contra `pg_catalog` e `information_schema`.
Nenhuma delas toca tabelas de aplicação do cliente.

| Heurística | Objeto consultado | Dado lido |
|---|---|---|
| Extensão pgvector / pgml | `pg_extension` | nome + versão da extensão |
| Colunas `vector(N)` | `pg_attribute + pg_class + pg_namespace` | schema.tabela.coluna + dimensão |
| Índices HNSW/IVFFLAT | `pg_indexes` | schema, tabela, nome do índice, DDL do índice |
| Schemas ML | `pg_namespace` | nome do schema |
| MLflow tracking | `information_schema.tables` | nomes das tabelas |
| Tabelas suspeitas | `information_schema.tables` | schema.tabela |
| Colunas suspeitas | `information_schema.columns` | schema.tabela.coluna + tipo |

**Permissões mínimas recomendadas pro usuário do agent:**

```sql
-- Usuário dedicado somente pra leitura de metadados.
-- Não precisa ter SELECT em nenhuma tabela de aplicação.
CREATE ROLE radar_readonly WITH LOGIN PASSWORD '<gere uma forte>';
GRANT USAGE ON SCHEMA pg_catalog, information_schema TO radar_readonly;
-- Fim. Não dê SELECT em outras schemas.
```

Assim, mesmo que o agent fosse comprometido, o atacante só conseguiria ler
metadados (o que o próprio Radar já veria) — zero superfície de exfiltração
de dados de aplicação.

## Modelo de ameaça resumido

| Ameaça | Mitigação |
|---|---|
| Radar Cloud comprometido | Só vê metadados; credenciais do cliente ficam intactas. |
| Canal WS interceptado | Use WSS (TLS); o payload não carrega credenciais mesmo em claro. |
| Cloud envia task maliciosa | Agent aceita apenas `type` whitelisted (`welcome`, `heartbeat_ack`, `scan_task`). Nunca executa código arbitrário. |
| Agent comprometido na máquina do cliente | Credencial é read-only de metadados → atacante não acessa dados. Atualizações assinadas via GHCR. |
| `/_debug/ws-log` vazando frames | Endpoint só existe com `DEBUG_WS_LOG=true`. Em produção a env var é desligada → endpoint retorna 404, log fica vazio. |

## Como validar você mesmo

No seu ambiente, sem precisar confiar em nenhum documento:

```powershell
$env:DEBUG_WS_LOG="true"
docker compose down -v
docker compose up --build -d
Start-Sleep -Seconds 15
python tests/security/verify_no_credential_leak.py
```

O script gera `tests/security/report.md` com o veredito e a tabela completa
de frames capturados. Se algum fragmento de credencial for encontrado, o
script sai com código 1 e o relatório marca **FAIL**.

## Contato

Reporte vulnerabilidades de segurança a security@jumplabel.com.br
(placeholder — confirmar canal oficial).
