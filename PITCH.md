# Radar Agent — Proposta de arquitetura alternativa

**TL;DR** — Mudar o modelo "cliente cola credencial no cloud" para
"cliente instala agent na máquina dele, só os metadados voltam pra
gente". Destrava vendas em enterprise / setor regulado, resolve
ambientes air-gapped, reduz blast radius do nosso cloud. A POC
funciona, tem comparativo vs. Radar atual, tem prova empírica de que
a credencial não trafega, e tem demo ao vivo pronta.

---

## Problema

Clientes reclamam de colar credencial de produção no nosso cloud.
Isso tem três consequências concretas:

1. **Trava vendas** em enterprise, bancos, saúde, governo — CISO não
   aprova entrega de credencial pra SaaS externa.
2. **Reduz nosso TAM** — não conseguimos escanear sistemas on-premise
   ou air-gapped que não têm saída de internet.
3. **Concentra risco em nós** — se o nosso cloud for comprometido,
   vazam credenciais de todos os clientes simultaneamente.

A Alltrue / Varonis Atlas (adquirida por US$150M em Fev/2026) atacou
isso com network monitoring + AI gateway. Funciona mas enxerga de
fora — perde metadados ricos que só a API nativa do sistema entrega.

## Solução proposta

Modelo **Secure Agent**, inspirado no IICS da Informatica:

```
[Máquina do Cliente]                      [Radar Cloud]
┌─────────────────────────────────┐       ┌──────────────────────┐
│   Radar Agent (Docker image)    │  WSS  │  Control Plane       │
│  ┌───────────────────────────┐  │ ─────▶│                      │
│  │ Conector PostgreSQL, etc. │  │ ◀──── │  Dashboard + API     │
│  └───────────────────────────┘  │ out   │                      │
│  Credenciais ficam aqui         │ only  │  Recebe só metadados │
└─────────────────────────────────┘       └──────────────────────┘
```

Princípios:
- Agent *outbound-only* — firewalls corporativos permitem
- Credencial vive em env var no agent, **nunca** trafega no canal
- Cloud recebe só os assets descobertos (schema, tipo, dimensão…)
- Cobre ambientes air-gapped que a Alltrue não alcança

## Provas concretas da POC

Três critérios atacados. Tudo reprodutível em `agent-poc/`.

### 1. Paridade de discovery

Documentado em `docs/PARITY.md`. Testado contra o mesmo PostgreSQL.

| Capacidade | Radar cloud atual | Agent POC |
|---|:-:|:-:|
| Pattern textual em nome de tabela/coluna | ✅ 24 patterns | ⚠️ 14 (fácil portar) |
| Detecção de extensão `pgvector` | ❌ | ✅ |
| Detecção de tipo `vector(N)` + inferência de provedor | ❌ | ✅ |
| Índices vetoriais HNSW / IVFFLAT | ❌ | ✅ |
| MLflow tracking por assinatura de tabelas | ❌ | ✅ |
| Cobertura de múltiplos schemas | ❌ (só `public`) | ✅ |

**Resultado**: o agent acha **mais** que o Radar atual. Regride só em
patterns textuais (portáveis em ~45min) e ganha 5 capacidades novas.

### 2. Credencial nunca sai do cliente

Script `tests/security/verify_no_credential_leak.py` instrumenta o
WebSocket, dispara um scan completo, inspeciona cada frame em busca
de credencial. Último run: **PASS**, 3 frames analisados, zero leaks.
Relatório em `tests/security/report.md` — entregável pro CISO do
cliente sem modificar nada.

### 3. Onboarding é um `docker run`

Imagens publicadas em `ghcr.io/kauakestering26/radar-agent`. Cliente
roda:

```bash
docker run -d \
  -e CONTROL_PLANE_URL=wss://radar.nosso-dominio.com \
  -e AGENT_ID=cliente-x \
  -e POSTGRES_DSN=postgresql://radar_ro:xxx@db/app \
  ghcr.io/kauakestering26/radar-agent/agent:0.1.0
```

Sem clonar repo, sem instalar dependência, sem configurar nada no
cloud. 30 segundos do zero até aparecer no dashboard.

## Posicionamento vs. concorrência

| Dimensão | Radar atual | Radar Agent | Alltrue / Varonis Atlas |
|---|---|---|---|
| Credencial no nosso cloud | ✅ (risco) | ❌ (fica no cliente) | ❌ (proxy de rede) |
| Cobre air-gapped | ❌ | ✅ | ⚠️ (deploy on-prem pesado) |
| Metadado rico (API nativa) | ✅ | ✅ | ❌ (só tráfego de rede) |
| Fricção de onboarding | Baixa (cola credencial) | Média (docker run) | Alta (deploy on-prem) |
| Segmento alvo | SMB/mid | Mid/enterprise | Enterprise only |

Não mata o modelo atual — **coexistem**. SMB continua colando credencial
(onboarding em 5min). Mid/enterprise vai no agent (vende onde hoje
perdemos). Cria tier de pricing orgânico.

## Esforço estimado para integrar no Radar produção

| Marco | Tempo estimado |
|---|---|
| Auth mínima agent ↔ cloud (token compartilhado) | 1-2 dias |
| Connection Registry no cloud (cadastrar bancos do cliente por ID) | 3-4 dias |
| Dashboard de agents conectados no frontend do Radar | 2-3 dias |
| Persistência dos scan results em PostgreSQL | 1 dia |
| Próximos conectores (GitHub, K8s) seguindo o padrão | ~1 semana cada |

**Total pra MVP integrado**: ~2 semanas de trabalho pra ter um cliente
real testando com o Radar de produção rodando agent + cloud.

## Call to action

1. **Aprovação pra evoluir a POC** — estruturo no backlog, coloco como
   prioridade da próxima sprint.
2. **Identificar 1 cliente piloto** — preferência: alguém que já pediu
   "não posso colar credencial" antes. Ofereço demo de 15min.
3. **Decisão sobre open-source do agent** — hoje está com licença
   proprietary, mas publicar o agent como OSS (cloud fechado, agent
   aberto) é argumento de confiança pra enterprise e gera comunidade.

## Recursos

- **Repo público**: https://github.com/kauakestering26/radar-agent
- **Imagens Docker**: `ghcr.io/kauakestering26/radar-agent/{agent,control-plane}`
- **Dashboard demo**: sobe com `docker compose up` em 30s
- **Documentos**: `docs/PARITY.md` (comparativo), `docs/SECURITY.md`
  (pra CISO), `docs/DEMO.md` (roteiro de apresentação)
