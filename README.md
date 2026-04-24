# Radar Agent

Agent distribuído do **Radar AI** — roda na máquina do cliente, descobre ativos
de IA nos sistemas dele, e envia apenas os resultados ao Radar Cloud.

**Credenciais nunca saem do ambiente do cliente.**

> Repositório independente do Radar Cloud (stack FastAPI + Railway).
> O agent tem ciclo de release próprio: imagem Docker versionada, o cliente
> atualiza quando quiser.

## Arquitetura

```
[Máquina do Cliente]                    [Radar Cloud]
┌────────────────────────┐              ┌──────────────────────┐
│   Radar Agent          │  WebSocket   │  Control Plane       │
│  ┌──────────────────┐  │ ──────────► │  POST /scan/{id}     │
│  │ Scanner Engine   │  │ ◄────────── │  GET  /results       │
│  │ (conectores)     │  │  outbound   │  GET  /agents        │
│  └──────────────────┘  │    only     └──────────────────────┘
│  Credenciais ficam aqui│
└────────────────────────┘
```

- O agent **nunca recebe conexões** — só inicia conexões de saída (outbound-only),
  amigável a firewalls e proxies corporativos.
- Credenciais dos sistemas do cliente **jamais saem** do ambiente dele.
- O cloud recebe apenas os **resultados** (assets de IA descobertos).
- Cobre sistemas on-premise e air-gapped, que abordagens de network monitoring
  (Alltrue/Varonis Atlas) não alcançam.

## Quick start

```bash
# 1. (opcional) copia o template de variáveis
cp .env.example .env

# 2. sobe control-plane + agent
make up

# 3. dispara um scan mock e lista resultados
make scan
make results
```

Sem `make`, os comandos equivalentes estão em `docker compose up --build`
e nos `curl`s da seção abaixo.

## Comandos úteis (Makefile)

| Comando          | O que faz                                           |
| ---------------- | --------------------------------------------------- |
| `make up`        | Sobe control-plane + agent (com rebuild se preciso) |
| `make down`      | Derruba tudo                                        |
| `make logs`      | Segue logs em tempo real                            |
| `make scan`      | Dispara scan mock no `agent-cliente-1`              |
| `make scan-all`  | Dispara scan em todos os agents conectados          |
| `make results`   | Lista assets descobertos                            |
| `make agents`    | Lista agents conectados                             |
| `make health`    | Health check do control-plane                       |
| `make clean`     | Derruba + remove volumes e imagens locais           |

Variáveis sobrescrevíveis: `AGENT_ID`, `CONNECTOR`, `CONTROL_PLANE`.

```bash
make scan AGENT_ID=agent-cliente-2 CONNECTOR=mock
```

## API direta (curl)

```bash
# Scan num agent específico
curl -X POST http://localhost:8000/scan/agent-cliente-1 \
  -H "Content-Type: application/json" \
  -d '{"connector": "mock"}'

# Scan em todos os agents
curl -X POST http://localhost:8000/scan-all \
  -H "Content-Type: application/json" \
  -d '{"connector": "mock"}'

curl http://localhost:8000/results   # assets descobertos
curl http://localhost:8000/agents    # agents conectados
curl http://localhost:8000/health    # status
```

## Conectores disponíveis

| Conector     | Status  | O que detecta                                                                                                                        |
| ------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `mock`       | pronto  | Simula descoberta de 6 tipos de asset — usado para testar o pipeline sem credenciais reais.                                          |
| `postgresql` | pronto  | pgvector, colunas `vector(N)`, índices HNSW/IVFFLAT, schemas ML, MLflow tracking tables, pgml, tabelas/colunas com nomes suspeitos. |
| `github`     | roadmap | Workflows de Actions chamando OpenAI/Anthropic, arquivos `.pkl`/`.safetensors`, `requirements.txt` com libs ML.                      |
| `kubernetes` | roadmap | Pods com labels `model-serving`, secrets `OPENAI_API_KEY`, workloads de Triton/KServe.                                               |

### PostgreSQL — exemplo completo

O target `postgres-target` do `docker-compose.yml` sobe um Postgres com
pgvector e um seed que dispara todas as heurísticas. Basta subir tudo:

```bash
make up                       # control-plane + agent + postgres-target
make scan-postgres            # dispara scan do conector postgresql
make results                  # lista os assets descobertos
```

Esperado: ~10+ assets — extensão `pgvector`, duas colunas `vector(N)` com
dimensões de OpenAI, dois índices vetoriais, MLflow tracking detectado,
schemas ML (`ml`, `mlflow`, `feast`, `feature_store`), tabelas suspeitas
(`prompts_log`, `ml_predictions`), colunas suspeitas (`tokens_input`,
`completion`, etc.).

**Contra cliente real**: aponte o agent pra um Postgres do cliente via env var:

```bash
# no .env do cliente (nunca sai da máquina dele)
POSTGRES_DSN=postgresql://radar_readonly:xxx@db.cliente.internal:5432/app
```

Permissões mínimas recomendadas pro usuário `radar_readonly`:

```sql
-- Read-only nas views de metadados que o conector consulta:
GRANT USAGE ON SCHEMA pg_catalog, information_schema TO radar_readonly;
-- Sem SELECT em dados da aplicação — o conector nunca lê linhas de usuário.
```

O conector **não lê dados de aplicação** — só consulta `pg_catalog`,
`information_schema` e `pg_extension`. Zero superfície de exfiltração.

Filtros opcionais via task:

```bash
curl -X POST http://localhost:8000/scan/agent-cliente-1 \
  -H "Content-Type: application/json" \
  -d '{"connector": "postgresql", "config": {"schemas": ["public","ml"], "sample_rows": true}}'
```

### Por que isso ganha da Alltrue/Varonis Atlas

Alltrue enxerga de fora via proxy de rede. O conector do Radar consulta a
API nativa do Postgres e responde perguntas que o proxy não consegue:

- "Existe busca vetorial em produção?" → olha `pg_indexes` com `hnsw/ivfflat`
- "Qual provedor de embedding está em uso?" → infere pela dimensão da coluna
- "Há MLflow tracking neste banco?" → identifica pela assinatura de tabelas

Tudo sem tráfego pra analisar, funciona inclusive em air-gapped.

## Simular múltiplos clientes

Descomente o serviço `agent-2` em `docker-compose.yml` e rode `make up`.

## Estrutura

```
agent-poc/
├── .github/workflows/build.yml   ← CI: build+push de imagens no ghcr.io
├── .env.example                  ← template de variáveis (copie para .env)
├── .gitignore
├── docker-compose.yml
├── Makefile
├── README.md
├── VERSION                       ← versão semântica atual
├── control-plane/
│   ├── main.py                   ← FastAPI: WebSocket + REST API
│   ├── requirements.txt
│   ├── .dockerignore
│   └── Dockerfile
├── agent/
│   ├── main.py                   ← Agent: conecta, recebe tasks, executa scans
│   ├── requirements.txt
│   ├── .dockerignore
│   ├── Dockerfile
│   └── connectors/
│       ├── mock_scanner.py       ← Simula descoberta — útil pra testar pipeline
│       └── postgresql.py         ← Conector real: pgvector, MLflow, ML schemas, etc.
└── targets/
    └── postgres-test/init/       ← Seed SQL do target de teste (pgvector)
```

## Release flow

Versionamento semântico (`MAJOR.MINOR.PATCH`), fonte de verdade em `VERSION`.
Cada tag `vX.Y.Z` empurrada pro GitHub dispara o workflow `.github/workflows/build.yml`
e publica as imagens em:

```
ghcr.io/<owner>/<repo>/agent:<version>
ghcr.io/<owner>/<repo>/control-plane:<version>
```

Processo de release:

```bash
# 1. bumpar versão
echo "0.2.0" > VERSION

# 2. commitar + taguear
git add VERSION
git commit -m "release: 0.2.0"
git tag v0.2.0
git push origin main --tags
```

## Separação do Radar Cloud

Este repo é **independente** do repo principal do Radar (backend/frontend/docs
que sobem no Railway). As duas razões:

1. O agent tem ciclo de release próprio — o cliente decide quando atualizar
   a imagem que roda na infra dele. Não faz sentido acoplar ao deploy do cloud.
2. Build context do agent não toca em código de credenciais/segredos do cloud —
   reduz superfície de ataque numa imagem que vai rodar fora do nosso perímetro.

No repo do Radar principal, a pasta `agent-poc/` está listada no `.gitignore`
pra garantir que nada vaze no Railway.

## Roadmap

Curto prazo — evoluir a POC:

- [ ] Autenticação agent ↔ control plane (token compartilhado, depois JWT/mTLS)
- [x] Primeiro conector real — PostgreSQL (pgvector, MLflow, schemas ML)
- [ ] Persistência no Control Plane (PostgreSQL — hoje é memória)
- [ ] Próximos conectores: GitHub, Kubernetes, AWS (IAM + Bedrock), OpenAI (org-level)

Médio prazo:

- [ ] Fila de tasks (Redis ou RabbitMQ) com retry automático
- [ ] Criptografia dos resultados antes do envio ao cloud
- [ ] Instalador do agent (systemd / Windows Service)
- [ ] Dashboard simples para visualizar agents + resultados

Longo prazo:

- [ ] Substituir modelo atual (credenciais no cloud) pelo modelo de agent
- [ ] Monitoramento contínuo via agent (watch/stream em vez de scan periódico)
- [ ] Multi-tenant: mais de um agent por cliente, com pools por workload
