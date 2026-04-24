# Radar Agent POC — atalhos de desenvolvimento
#
# Uso:
#   make up          # sobe control-plane + agent
#   make down        # derruba tudo
#   make logs        # logs em tempo real
#   make scan        # dispara scan mock no agent-cliente-1
#   make results     # lista assets descobertos
#   make agents      # lista agents conectados
#   make health      # health check do control-plane
#   make clean       # derruba + limpa volumes + imagens

COMPOSE        ?= docker compose
AGENT_ID       ?= agent-cliente-1
CONNECTOR      ?= mock
CONTROL_PLANE  ?= http://localhost:8000

.PHONY: help up down restart logs build rebuild ps \
        scan scan-all results results-clear agents health \
        clean

help:
	@echo "Alvos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

# ── Ciclo de vida dos containers ─────────────────────────────────────────────

up: ## Sobe control-plane + agent (com rebuild se necessário)
	$(COMPOSE) up --build -d

down: ## Derruba todos os containers
	$(COMPOSE) down

restart: down up ## Reinicia tudo

logs: ## Segue logs em tempo real
	$(COMPOSE) logs -f

build: ## Build das imagens sem subir
	$(COMPOSE) build

rebuild: ## Build forçando sem cache
	$(COMPOSE) build --no-cache

ps: ## Status dos containers
	$(COMPOSE) ps

# ── Interações com o Control Plane ───────────────────────────────────────────

scan: ## Dispara scan no agent (AGENT_ID, CONNECTOR)
	curl -s -X POST $(CONTROL_PLANE)/scan/$(AGENT_ID) \
	  -H "Content-Type: application/json" \
	  -d '{"connector": "$(CONNECTOR)"}' | python -m json.tool

scan-postgres: ## Scan do conector postgresql (atalho)
	$(MAKE) scan CONNECTOR=postgresql

scan-all: ## Dispara scan em todos os agents
	curl -s -X POST $(CONTROL_PLANE)/scan-all \
	  -H "Content-Type: application/json" \
	  -d '{"connector": "$(CONNECTOR)"}' | python -m json.tool

results: ## Lista todos os assets descobertos
	curl -s $(CONTROL_PLANE)/results | python -m json.tool

results-clear: ## Limpa os resultados em memória
	curl -s -X DELETE $(CONTROL_PLANE)/results | python -m json.tool

agents: ## Lista agents conectados
	curl -s $(CONTROL_PLANE)/agents | python -m json.tool

health: ## Health check do control-plane
	curl -s $(CONTROL_PLANE)/health | python -m json.tool

# ── Limpeza ──────────────────────────────────────────────────────────────────

clean: ## Derruba + remove volumes e imagens do projeto
	$(COMPOSE) down -v --rmi local
