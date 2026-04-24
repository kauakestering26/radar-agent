# DEV Runbook — dia da demo (PC 1)

> Checklist e comandos prontos pra mim (Kauã) seguir em ordem cronológica no
> dia da demo. PC 1 = minha máquina Windows, onde roda o control-plane +
> dashboard + Cloudflare tunnel.

---

## 15:30 — Pre-flight (30 min antes)

Abre dois PowerShells. Deixa ambos abertos até o fim da reunião.

### Terminal A — control-plane + dashboard

```powershell
cd C:\projetos\RadarControlA\RadarAiControl\agent-poc

# Reset limpo
docker compose down -v

# Sobe com tap de segurança ativo (pra caso queira demonstrar o script)
$env:DEBUG_WS_LOG="true"
docker compose up --build -d

Start-Sleep -Seconds 12

# Sanity check — precisa retornar debug_ws_log_enabled: True
Invoke-RestMethod http://localhost:8000/health

# Abre o dashboard
Start-Process http://localhost:8000
```

### Terminal B — Cloudflare tunnel

```powershell
cloudflared tunnel --url http://localhost:8000
```

**Copia a URL** `https://xxx-yyy-zzz.trycloudflare.com` que ele imprimir.

**NÃO FECHA ESTE TERMINAL** — se fechar, a URL morre.

### Confirmações finais

- [ ] Abre `https://xxx-yyy-zzz.trycloudflare.com` no navegador → dashboard carrega?
- [ ] Dashboard mostra 1 agent (`agent-cliente-1`) conectado?
- [ ] Assets estão zerados? (se não, clica em "Limpar")
- [ ] Desativa "dormir" do Windows: Configurações → Energia → Nunca dormir
- [ ] Abre abas no navegador (apoio): `PITCH.md`, `docs/PARITY.md`, `docs/SECURITY.md`, `docs/DEMO.md`, `tests/security/report.md`

---

## 15:40 — Mensagem pro dono

Manda no chat da reunião ou WhatsApp:

> Oi [nome], pra demo de 16h eu vou precisar que você rode um container
> Docker pequeno no seu Mac. Zero credencial sua é usada, zero instalação
> permanente. Só precisa **Docker Desktop** rodando.
>
> Se ainda não tem, instala em: https://www.docker.com/products/docker-desktop/
>
> Na hora da call, cola isso no Terminal do Mac:
>
> ```bash
> mkdir -p ~/radar-demo && cd ~/radar-demo
> curl -O https://raw.githubusercontent.com/kauakestering26/radar-agent/main/docker-compose.demo.yml
> export CONTROL_PLANE_URL="wss://<URL-DO-MEU-TUNNEL>.trycloudflare.com"
> export AGENT_ID="notebook-dono"
> docker compose -f docker-compose.demo.yml up -d
> ```
>
> Primeira vez demora ~1-2 min baixando imagens. Me avisa quando terminar e
> eu mostro o resto.

> ⚠ **Substitui `<URL-DO-MEU-TUNNEL>` pela URL real do Cloudflare do Terminal B.**

---

## 15:55 — Último check 5 min antes

- [ ] Tunnel ainda ativo? (refresh na URL do tunnel no navegador)
- [ ] Dashboard ainda limpo?
- [ ] Containers OK? `docker compose ps` — 3 Up
- [ ] PC vai dormir? (não)

---

## 16:00 — Demo (5 min)

Segue `docs/DEMO.md` — tem o roteiro narrativa por etapa.

Resumo rápido:

| Tempo | Etapa | O que fazer |
|---|---|---|
| 0:00-0:30 | Problema | Narrativa sobre credencial + objeção CISO |
| 0:30-1:00 | Dashboard | Mostra dashboard com 1 agent (`agent-cliente-1`) |
| 1:00-3:00 | Agent dele sobe | Ele cola o bloco, aparece 2º card no dashboard |
| 3:00-5:00 | Scan + leak proof | Clica Scan, 26 assets aparecem, roda `verify_no_credential_leak.py` |
| 5:00-5:30 | Fechamento | CTA (libera sprint? cliente piloto?) |

---

## Se ele pedir pra conectar com o banco REAL dele

Isso é o "você me convenceu, agora me mostra com meu banco". Orienta ele
em tempo real:

### Opção 1 — banco local no Mac dele (mais provável)

Peça pra ele rodar no mesmo terminal (sem derrubar o que tá rodando):

```bash
# 1. Derruba o setup atual
docker compose -f docker-compose.demo.yml down -v

# 2. Aponta POSTGRES_DSN pro banco local dele
export POSTGRES_DSN="postgresql://USUARIO:SENHA@host.docker.internal:5432/NOMEDB"

# 3. (mantém as outras env vars)
export CONTROL_PLANE_URL="wss://<URL-TUNNEL>.trycloudflare.com"
export AGENT_ID="notebook-dono-real-db"

# 4. Sobe de novo
docker compose -f docker-compose.demo.yml up -d
```

> `host.docker.internal` é a forma que o container "enxerga" o localhost do Mac.

### Opção 2 — banco no cloud dele (RDS, Neon, Supabase)

```bash
export POSTGRES_DSN="postgresql://USUARIO:SENHA@host.rds.amazonaws.com:5432/prod?sslmode=require"
```

### Se ele não tiver role read-only

Pede pra ele rodar isso no banco dele antes:

```sql
CREATE ROLE radar_readonly WITH LOGIN PASSWORD 'escolhe-uma';
GRANT USAGE ON SCHEMA pg_catalog, information_schema TO radar_readonly;
-- e SÓ isso. Não precisa dar SELECT em mais nada.
```

Argumento pra ele: "o conector só lê metadados do catálogo. Mesmo que comprometam o binário, não acessam dado nenhum da aplicação."

### Depois de subir apontando pro banco real

No seu dashboard, clica **"Scan Postgres"** no card dele novamente. Agora os
assets que aparecerem refletem o banco REAL dele — schemas, extensões, tipos
de coluna, índices verdadeiros. É a demo mais forte possível.

### Se NÃO achar nada de IA no banco dele

Acontece — ambiente de produção sem ML explícito. Use como oportunidade:

> "Olha, no seu ambiente hoje não tem pgvector instalado nem vetor em tabela.
> Isso também é informação valiosa: te diz que o time ainda não tá usando
> IA nesse banco. Quando começarem, a gente capta na hora. O agent é pra
> rodar **contínuo**, não uma vez só."

---

## Plano B — se o dono não conseguir rodar no Mac dele

### Cenário: Docker Desktop travou, firewall bloqueando, ou ele não conseguiu instalar

Sobe uma **segunda instância do compose.demo na tua máquina** simulando o
notebook dele:

```powershell
# Em OUTRO PowerShell na tua máquina
cd ~
mkdir -p radar-fake-guest -Force
cd radar-fake-guest
curl.exe -O https://raw.githubusercontent.com/kauakestering26/radar-agent/main/docker-compose.demo.yml

# Aponta pra localhost mesmo (não precisa de tunnel se é na mesma máquina)
$env:CONTROL_PLANE_URL="ws://host.docker.internal:8000"
$env:AGENT_ID="simulando-notebook-dono"

docker compose -f docker-compose.demo.yml up -d
```

Narra: *"Tá rodando aqui na minha máquina agora simulando o que seria no seu
notebook. O fluxo é idêntico — olha, aparece como agent separado no
dashboard."*

Perde a viralidade de "tá no seu PC", mas a história técnica fica igual.

---

## 16:30 (ou quando acabar a reunião) — Desmontar

```powershell
# Terminal A
cd C:\projetos\RadarControlA\RadarAiControl\agent-poc
docker compose down -v

# Terminal B — Ctrl+C pra matar o cloudflared

# Se rodou o plano B:
cd ~\radar-fake-guest
docker compose -f docker-compose.demo.yml down -v
```

Se ele vai continuar testando no Mac dele, deixa o control-plane rodando e
a URL do tunnel ativa. Só derruba quando ele confirmar que já tirou o
compose dele.
