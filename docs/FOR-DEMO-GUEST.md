# Radar Agent — Demo (guia pro convidado)

> Isso aqui é o que você manda pro dono (ou qualquer pessoa que vá rodar
> o agent numa máquina diferente da sua) antes da demo. Texto pronto pra
> copiar/colar no WhatsApp, email ou doc.

---

## Mensagem sugerida

> **Assunto**: Demo do Radar Agent — o que você precisa na sua máquina
>
> Oi [nome],
>
> Pra gente fazer a demo do Radar Agent, você roda um container pequeno
> no seu notebook e eu vejo os resultados no meu dashboard em tempo
> real. Credencial nunca sai do seu lado.
>
> **Você precisa ter:**
>
> 1. **Docker Desktop** instalado e rodando
>    Download: https://www.docker.com/products/docker-desktop/
>    (Windows, Mac e Linux — instala, reinicia, abre Docker Desktop e
>    espera o ícone ficar verde na bandeja)
>
> 2. Um terminal qualquer (PowerShell no Windows já vem)
>
> Só isso. Sem Python, sem Git, sem nada pra instalar.
>
> **Passo a passo no dia:**
>
> Vou te mandar na hora:
> - Um arquivo chamado `docker-compose.demo.yml`
> - Uma URL pro meu control-plane (tipo `wss://radar-dev.trycloudflare.com`)
>
> Você:
>
> 1. Salva o arquivo numa pasta qualquer
> 2. Edita UMA linha dele: trocar `CHANGE_ME` pela URL que eu te mandei
> 3. Abre o terminal naquela pasta e roda:
>
>    ```
>    docker compose -f docker-compose.demo.yml up -d
>    ```
>
> 4. Me avisa. Aí dou refresh no meu dashboard e seu notebook aparece
>    conectado. Em ~3 minutos a gente valida o fluxo inteiro.
>
> No fim da demo, pra limpar tudo:
>
> ```
> docker compose -f docker-compose.demo.yml down -v
> ```
>
> Isso remove o container e qualquer dado de teste. Zero resíduo na sua máquina.

---

---

## Parte 2 — Apontar pro banco REAL dele (se ele pedir)

Se o dono disser *"ok, funciona, agora me mostra com um banco meu"*, você
só troca a env var `POSTGRES_DSN` antes do `docker compose up`. Os comandos
ficam:

### Cenário A — banco na própria máquina dele (localhost)

Ex: Postgres Docker local, ou Postgres nativo rodando no Mac dele.

**Mac/Linux:**
```bash
export POSTGRES_DSN="postgresql://usuario:senha@host.docker.internal:5432/nome_do_db"
docker compose -f docker-compose.demo.yml up -d
```

**Windows:**
```powershell
$env:POSTGRES_DSN="postgresql://usuario:senha@host.docker.internal:5432/nome_do_db"
docker compose -f docker-compose.demo.yml up -d
```

> `host.docker.internal` é como o container enxerga o `localhost` da máquina
> host. Se o banco dele está em `localhost:5432`, use esse endereço.

### Cenário B — banco em servidor interno / VPN

Se o banco é acessível pela rede dele:

```bash
export POSTGRES_DSN="postgresql://usuario:senha@db.interna.empresa:5432/app"
docker compose -f docker-compose.demo.yml up -d
```

O Docker Desktop usa a mesma stack de rede do host, então se o Mac dele
alcança o banco via hostname/IP, o container também alcança.

### Cenário C — banco no cloud (RDS, Neon, Supabase, Railway)

```bash
export POSTGRES_DSN="postgresql://usuario:senha@xxx.rds.amazonaws.com:5432/prod?sslmode=require"
docker compose -f docker-compose.demo.yml up -d
```

> Se o banco exigir TLS, manda `?sslmode=require` no final da DSN. asyncpg
> respeita isso por padrão.

### Permissões mínimas SQL (recomendar pro dono)

O conector **só lê metadados** — nunca toca dados de aplicação. Permissão
absoluta mínima:

```sql
CREATE ROLE radar_readonly WITH LOGIN PASSWORD '<escolha uma>';
GRANT USAGE ON SCHEMA pg_catalog, information_schema TO radar_readonly;
-- e pronto. Não dê SELECT em nenhuma tabela de aplicação.
```

Argumento pro CISO dele: mesmo que o agent seja comprometido ou alguém
pegue o binário da imagem, só conseguiria ler catálogo. Zero superfície
de exfiltração de dados.

### Formato alternativo — docker run puro (mais simples ainda)

Se ele quiser ir direto ao ponto sem `docker-compose.demo.yml`:

```bash
docker run -d --rm --name radar-agent \
  -e CONTROL_PLANE_URL="wss://seu-tunnel.trycloudflare.com" \
  -e AGENT_ID="cliente-xyz" \
  -e POSTGRES_DSN="postgresql://radar_ro:senha@host.docker.internal:5432/app" \
  ghcr.io/kauakestering26/radar-agent/agent:0.2.0
```

Um único comando, zero arquivo. É exatamente esse o "modelo de deploy"
final do produto: o cliente roda um `docker run` e esquece.

---

## Checklist interno (pro dev, véspera da demo)

- [ ] Enviei o `docker-compose.demo.yml` pro convidado
- [ ] Enviei a URL do control-plane pro convidado (rede local ou Cloudflare tunnel)
- [ ] Convidado confirmou que o Docker Desktop está rodando na máquina dele
- [ ] Meu control-plane está de pé em `http://localhost:8000` com dashboard abrindo
- [ ] Testei a URL que mandei pra ele (do próprio celular ou outra máquina)
- [ ] `docs/DEMO.md` aberto no meu segundo monitor
- [ ] `tests/security/report.md` aberto pra mostrar o PASS
- [ ] `docs/PARITY.md` e `PITCH.md` abertos como apoio
