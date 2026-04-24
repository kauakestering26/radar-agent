# Roteiro de Demo — Radar Agent

> Objetivo: mostrar em ~5 minutos que o agent descobre ativos de IA na
> máquina do cliente **sem que a credencial saia de lá**, e que o resultado
> aparece em tempo real no dashboard do Radar.

---

## Cenário da demo

```
        MÁQUINA DO DONO                      SUA MÁQUINA (dev)
┌──────────────────────────┐             ┌──────────────────────┐
│                          │             │                      │
│   docker run (agent)     │             │  docker compose      │
│   ── conecta no Postgres │             │  ── control-plane    │
│      local dele          │             │  ── dashboard :8000  │
│   ── envia metadados ────┼─── WSS ────▶│  ── postgres-target  │
│                          │  outbound   │     (só pra você     │
│   CREDENCIAL FICA AQUI   │    only     │      poder demonstrar│
│                          │             │      sem o Postgres  │
│                          │             │      dele)           │
└──────────────────────────┘             └──────────────────────┘
```

O ponto narrativo forte: ele roda algo NO notebook dele (credencial dele,
banco dele), você vê o resultado em tempo real no SEU dashboard, e o canal
entre os dois só carrega metadados.

---

## Preparação (faz 15 min antes da reunião)

### 1. Sobe o control-plane com dashboard

No seu PowerShell, dentro de `agent-poc/`:

```powershell
docker compose down -v
docker compose up --build -d
Start-Sleep -Seconds 10
```

Abre `http://localhost:8000` no navegador. Deve aparecer o **dashboard
"Radar Agent — Control Plane"** com 1 agent conectado (o seu `agent-cliente-1`).
Deixa essa aba aberta.

### 2. Expõe o control-plane pro notebook do dono

Duas opções — escolha uma:

#### Opção A — mesma rede Wi-Fi (demo presencial)

Descubra seu IP local:

```powershell
ipconfig | Select-String "IPv4"
```

Anote o IP (ex: `192.168.1.42`). O dono vai apontar o agent dele pra
`ws://192.168.1.42:8000`.

> Se o Windows Firewall reclamar quando o agent tentar conectar, libera
> a porta 8000 pra rede privada. Normalmente aparece um popup na primeira
> tentativa e é só clicar em "Permitir".

#### Opção B — túnel público (demo remota via call)

Use **Cloudflare Tunnel** (grátis, sem cadastro):

```powershell
# 1. Baixa o cloudflared uma vez (se ainda não tiver)
winget install --id Cloudflare.cloudflared

# 2. Abre um túnel pra sua porta 8000
cloudflared tunnel --url http://localhost:8000
```

Ele vai imprimir uma URL tipo `https://xxx-yyy-zzz.trycloudflare.com`.
Copia. É dessa URL que o agent do dono vai conectar, usando `wss://...`.

### 3. Ensaia o comando que o dono vai colar

Dois copy-paste prontos (um pro cenário A, outro pro B). Testa num segundo
terminal da tua própria máquina pra garantir que funciona antes da reunião.

### 4. Limpa os resultados do scan de preparação

No dashboard, botão **"Limpar"** no canto superior dos assets. Começa do zero.

---

## Na hora da demo

### Etapa 1 — Problema (30s)

> "Hoje o cliente precisa colar a credencial do banco no Radar cloud.
> Isso trava vendas em enterprise, em qualquer empresa com CISO sério,
> em qualquer setor regulado (financeiro, saúde, governo). Também nos
> impede de escanear bancos air-gapped. A alternativa é rodar um pequeno
> programa no ambiente do cliente — credencial fica lá, só os metadados
> vêm pra gente. Modelo que a Informatica usa no IICS. Vou mostrar
> funcionando."

### Etapa 2 — O dashboard já está aqui (30s)

Abre `http://localhost:8000` na tua tela. Aponta pro painel:

> "Esse é o control-plane — seria nosso cloud. Hoje tem 1 agent conectado
> que é o de teste, mas vou adicionar o *seu notebook* como segundo agent
> agora."

### Etapa 3 — Agent no notebook do dono (1-2min)

No notebook dele, abre um PowerShell/terminal e cola:

**Cenário A (rede local):**

```powershell
docker run -d --rm --name radar-agent `
  -e CONTROL_PLANE_URL=ws://192.168.1.42:8000 `
  -e AGENT_ID=agent-notebook-do-dono `
  -e POSTGRES_DSN=postgresql://radar:radar@host.docker.internal:5432/radar_test `
  ghcr.io/kauakestering26/radar-agent/agent:0.1.0
```

> *Substitua o IP e o POSTGRES_DSN pelo banco real do dono, ou use um
> Postgres local no notebook dele só pra demo (instala rápido via Docker
> Desktop ou ele pode usar um container `pgvector/pgvector:pg16` local).*

**Cenário B (túnel Cloudflare):**

```powershell
docker run -d --rm --name radar-agent `
  -e CONTROL_PLANE_URL=wss://xxx-yyy.trycloudflare.com `
  -e AGENT_ID=agent-notebook-do-dono `
  -e POSTGRES_DSN=postgresql://radar:radar@host.docker.internal:5432/radar_test `
  ghcr.io/kauakestering26/radar-agent/agent:0.1.0
```

Aponta pra tua tela:

> "Olha, o dashboard já detectou o segundo agent conectado. **Zero
> configuração no nosso lado** — ele apareceu só por causa do `docker
> run` que você rodou aí."

### Etapa 4 — Dispara o scan e narra (2min)

Clica em **"Scan Postgres"** no card do agent do dono.

> "O cloud acabou de mandar uma task — 'escaneie seu Postgres'. O agent
> agora tá conectando no banco na sua máquina, usando a credencial que
> só você tem. Essa credencial nem passa perto da gente."

Os assets começam a aparecer. Narra 2-3 assets concretos:

> "Olha aqui: achou a extensão pgvector v0.8.2 — sinal forte de que você
> tem busca vetorial em produção. Aqui achou uma coluna `vector(1536)` —
> a dimensão indica que você tá usando OpenAI ada-002. Aqui um índice
> HNSW — confirma busca semântica em produção. Aqui detectou MLflow
> tracking pela assinatura das tabelas, achou 6 tabelas típicas no mesmo
> schema. Tudo isso o Radar atual não consegue ver."

### Etapa 5 — A prova de que nada vazou (1min)

Volta pro teu terminal:

```powershell
python tests\security\verify_no_credential_leak.py
```

Aponta pro output `[PASS] ... zero leaks`:

> "Esse script captura cada frame WebSocket trocado entre o agent e o
> cloud e procura por credencial. Acabou de confirmar: nada vazou. Esse
> relatório você pode entregar pro CISO do cliente e encerrar a objeção."

### Etapa 6 — Fechamento (30s)

> "Resumindo: o agent descobre mais do que o Radar atual em Postgres,
> funciona em air-gapped, e resolve a objeção de credencial. Código
> está em `github.com/kauakestering26/radar-agent`, imagem Docker
> publicada. Próximo passo seria integrar isso ao Radar de produção —
> estimo X sprints. Libera?"

---

## Opcional — demo comparativa direta (se ele for cético)

Se o dono pedir "mas o Radar cloud não acha isso também?":

1. No Radar cloud em produção, crie uma conexão apontando pro mesmo
   Postgres de teste (requer expor o container `postgres-target` via
   `docker compose up` + port-forward ou ngrok de 5432).
2. Roda o scan lá, mostra o resultado.
3. Compare lado a lado com o dashboard do agent.
4. Abre `docs/PARITY.md` — a matriz explica o porquê.

Leva 3-5 min adicionais, só vale se ele pedir prova dura.

---

## Pós-demo

- Parar o agent do notebook: `docker stop radar-agent`
- Parar teu ambiente: `docker compose down -v`
- Se usou Cloudflare tunnel: `Ctrl+C` no terminal do `cloudflared`

---

## Checklist de véspera

- [ ] `docker compose up --build -d` roda sem erro no notebook do dev
- [ ] Dashboard abre em `http://localhost:8000` e mostra 1 agent
- [ ] `ipconfig` mostra o IP e firewall libera porta 8000 (cenário A) OU
      `cloudflared tunnel` abre com URL válida (cenário B)
- [ ] Comando `docker run` do agent testado num segundo terminal, aparece
      como agent #2 no dashboard
- [ ] `python tests\security\verify_no_credential_leak.py` → PASS
- [ ] `docs/PARITY.md` e `PITCH.md` abertos em abas pro caso de perguntas
- [ ] Dashboard limpo antes da reunião começar
