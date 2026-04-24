# GUEST Runbook — como entrar na demo (PC 2)

> Pra quem vai rodar o Radar Agent no próprio notebook durante a demo.
> Leva ~3 minutos de setup na primeira vez.

---

## Antes da demo — pré-requisito único

**Docker Desktop instalado e rodando.**

- Mac / Windows / Linux → https://www.docker.com/products/docker-desktop/
- Depois de instalar, abre o Docker Desktop e espera o ícone ficar **verde**
  na bandeja (canto superior direito no Mac, canto inferior direito no
  Windows).

Teste opcional de 30 segundos pra confirmar que tá funcionando:

```bash
docker run --rm hello-world
```

Se imprimir "Hello from Docker!", tudo certo. Se der erro, reinicia o
Docker Desktop antes da reunião.

**Você NÃO precisa de:** Git, Python, Node, banco instalado, SSH aberto,
VPN. Só Docker Desktop.

---

## Na hora da demo — 3 passos

O Kauã vai te mandar 1 coisa:

- A **URL do Cloudflare tunnel** dele, tipo `https://xxx.trycloudflare.com`

### 1. Abre o Terminal

- **Mac:** Cmd+Space → "Terminal" → Enter
- **Windows:** tecla Windows → "PowerShell" → Enter

### 2. Cola o bloco abaixo

Substitua a URL `wss://xxx.trycloudflare.com` pela URL que ele te mandou.

**Mac / Linux:**

```bash
mkdir -p ~/radar-demo && cd ~/radar-demo
curl -O https://raw.githubusercontent.com/kauakestering26/radar-agent/main/docker-compose.demo.yml
export CONTROL_PLANE_URL="wss://xxx.trycloudflare.com"
export AGENT_ID="notebook-dono"
docker compose -f docker-compose.demo.yml up -d
```

**Windows (PowerShell):**

```powershell
cd ~
mkdir radar-demo -Force
cd radar-demo
curl.exe -O https://raw.githubusercontent.com/kauakestering26/radar-agent/main/docker-compose.demo.yml
$env:CONTROL_PLANE_URL="wss://xxx.trycloudflare.com"
$env:AGENT_ID="notebook-dono"
docker compose -f docker-compose.demo.yml up -d
```

### 3. Avisa ele

Primeira vez, o Docker baixa 2 imagens (~500MB). Leva 1-2 min dependendo da
internet. Quando terminar, você vê algo como:

```
 ✔ Container radar-demo-postgres  Started
 ✔ Container radar-demo-agent     Started
```

Me avisa e eu te mostro o resultado no dashboard.

---

## Pra derrubar no fim

```bash
docker compose -f docker-compose.demo.yml down -v
```

Remove os dois containers e o volume de dados. Zero resíduo na sua máquina.

---

## Parte 2 — Apontar pro meu banco REAL (opcional)

Depois de ver a demo inicial (que usa um Postgres de teste), se quiser ver
com um banco de verdade seu, só trocar uma variável.

### Se o banco é LOCAL no seu Mac / Windows

```bash
# Mac/Linux:
docker compose -f docker-compose.demo.yml down -v
export POSTGRES_DSN="postgresql://USUARIO:SENHA@host.docker.internal:5432/NOMEDB"
export CONTROL_PLANE_URL="wss://xxx.trycloudflare.com"
export AGENT_ID="notebook-dono-banco-real"
docker compose -f docker-compose.demo.yml up -d
```

```powershell
# Windows:
docker compose -f docker-compose.demo.yml down -v
$env:POSTGRES_DSN="postgresql://USUARIO:SENHA@host.docker.internal:5432/NOMEDB"
$env:CONTROL_PLANE_URL="wss://xxx.trycloudflare.com"
$env:AGENT_ID="notebook-dono-banco-real"
docker compose -f docker-compose.demo.yml up -d
```

> `host.docker.internal` é como o container "enxerga" o localhost da sua
> máquina. Serve tanto pra Postgres nativo quanto pra Postgres em Docker
> local.

### Se o banco é CLOUD (RDS, Neon, Supabase, Railway, etc.)

Mesma coisa, só troca a DSN pelo endereço do seu banco:

```bash
export POSTGRES_DSN="postgresql://USUARIO:SENHA@xxx.rds.amazonaws.com:5432/prod?sslmode=require"
```

> Se o banco exige TLS (cloud geralmente exige), adiciona `?sslmode=require`
> no final da DSN.

### Se você não tiver um usuário read-only

Rode isso **no seu banco** antes — é a única coisa que o agent precisa:

```sql
CREATE ROLE radar_readonly WITH LOGIN PASSWORD 'troca-por-uma-forte';
GRANT USAGE ON SCHEMA pg_catalog, information_schema TO radar_readonly;
-- Só isso. Sem SELECT em tabela nenhuma da aplicação.
```

O conector do agent só consulta `pg_catalog` e `information_schema` —
metadados. Nunca lê dado de usuário. Mesmo que o binário fosse
comprometido, não tem superfície pra exfiltrar nada da aplicação.

---

## Perguntas comuns

**"O Kauã vai ter acesso à minha máquina?"**
Não. O agent abre conexão de dentro pra fora (outbound only), como um
navegador abrindo um site. Ele não tem nenhum jeito de entrar. Fecha o
terminal, desconecta.

**"Minha credencial chega no control-plane dele?"**
Não. Ela fica no env var do container, aqui na sua máquina. O canal entre
o agent e o control-plane só carrega metadados descobertos (schemas, tipos
de coluna, dimensões). Tem um script de verificação que prova isso
empiricamente — ele pode rodar ao vivo se você pedir.

**"E se eu tiver firewall corporativo?"**
O agent só precisa saída pra `*.trycloudflare.com:443` e `ghcr.io:443`.
Nenhum firewall corporativo padrão bloqueia isso. Se bloquear, testa em
rede doméstica.
