# Verificação de segurança — credenciais no WebSocket

- **Data**: 2026-04-24T11:34:22
- **Control plane**: `http://localhost:8000`
- **Agent alvo**: `agent-cliente-1`
- **Scan ID**: `84df0fc6`
- **Frames analisados**: 3
- **Tokens de credencial procurados**: 5
- **Palavras-chave sensíveis procuradas**: 5
- **Veredito**: **PASS**

## Metodologia

1. Control-plane sobe com `DEBUG_WS_LOG=true`, ativando um tap em
   memória que captura cada frame WS (in/out) com timestamp e payload.
2. Script limpa o log, dispara um scan PostgreSQL e espera o
   `scan_result` voltar — ou seja, o ciclo completo foi capturado.
3. Cada frame é serializado em JSON e inspecionado por substring
   match contra uma lista de tokens (credenciais do DSN default)
   e palavras-chave sensíveis (`password`, `POSTGRES_DSN`, etc.).
4. Se qualquer match → **FAIL**. Nenhum match → **PASS**.

## Tokens procurados

**Fragmentos de credencial** (matches são fatais):

- `radar:radar`
- `:radar@`
- `postgres-target:5432`
- `postgresql://`
- `postgres://`

**Palavras-chave sensíveis** (matches são fatais):

- `password`
- `passwd`
- `POSTGRES_DSN`
- `POSTGRES_PASSWORD`
- `secret_key`

## Frames capturados

| # | direção | tipo | tamanho | sample (primeiros 100 chars) |
|---|---------|------|---------|------------------------------|
| 0 | `out` | `scan_task` | 85B | `{"type": "scan_task", "scan_id": "84df0fc6", "connector": "postgresql", "config": {}}` |
| 1 | `in` | `scan_result` | 16101B | `{"type": "scan_result", "scan_id": "84df0fc6", "connector": "postgresql", "assets": [{"type": "vecto…` |
| 2 | `out` | `scan_ack` | 66B | `{"type": "scan_ack", "scan_id": "84df0fc6", "assets_received": 26}` |

## Leaks detectados

**Nenhum.** Nenhuma das credenciais conhecidas nem palavras-chave
sensíveis apareceram em qualquer frame WebSocket capturado.

Isso confirma a propriedade arquitetural central do agent:
**credenciais vivem só no ambiente do cliente e nunca trafegam
para o Radar Cloud**.

## Como reproduzir

```powershell
$env:DEBUG_WS_LOG="true"
docker compose down -v
docker compose up --build -d
Start-Sleep -Seconds 15
python tests/security/verify_no_credential_leak.py
```

---
_Gerado por_ `tests/security/verify_no_credential_leak.py`