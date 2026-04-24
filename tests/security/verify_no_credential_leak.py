#!/usr/bin/env python3
"""
Verificação empírica: nenhuma credencial do PostgreSQL trafega no WebSocket
entre agent e control-plane.

Como funciona:
  1. Liga o tap WS no control-plane (env DEBUG_WS_LOG=true já setado no compose).
  2. Limpa o log do tap.
  3. Dispara um scan PostgreSQL e espera o resultado completo chegar.
  4. Baixa todos os frames capturados.
  5. Procura em cada frame por tokens sensíveis (credencial do DSN default,
     palavras-chave como 'password', etc.).
  6. Gera `report.md` no mesmo diretório com o veredito.

Pré-requisitos pra rodar:
  - Ambiente de pé (`docker compose up --build -d`)
  - Variável DEBUG_WS_LOG=true passada ao control-plane. Em PowerShell:
        $env:DEBUG_WS_LOG="true"; docker compose up --build -d

Execução:
  python tests/security/verify_no_credential_leak.py

Exit code 0 = PASS, 1 = FAIL (credencial encontrada).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Configuração ─────────────────────────────────────────────────────────────
BASE = os.getenv("CONTROL_PLANE", "http://localhost:8000")
AGENT_ID = os.getenv("AGENT_ID", "agent-cliente-1")

# DSN default no docker-compose: postgresql://radar:radar@postgres-target:5432/radar_test
# Se NENHUM desses fragmentos aparecer em NENHUM frame, PASS.
SENSITIVE_TOKENS = [
    "radar:radar",          # user:password do DSN default
    ":radar@",              # password inline
    "postgres-target:5432", # host + port
    "postgresql://",        # prefixo de DSN
    "postgres://",          # prefixo alternativo
]

# Palavras-chave — se aparecerem em qualquer frame, é um sinal pra investigar.
# PASS só se ambas as listas ficam vazias.
SENSITIVE_KEYWORDS = [
    "password",
    "passwd",
    "POSTGRES_DSN",
    "POSTGRES_PASSWORD",
    "secret_key",
]

REPORT_PATH = Path(__file__).parent / "report.md"


# ── HTTP helpers (stdlib only) ───────────────────────────────────────────────

def _req(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, data=data, timeout=15) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return {"_error": str(e), "_status": e.code}
    except Exception as e:
        return {"_error": str(e)}


def _die(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(2)  # 2 = erro operacional, 1 fica pra leak detectado


# ── Etapas do teste ──────────────────────────────────────────────────────────

def step_precheck() -> None:
    print("== Pré-check ==")
    health = _req("GET", "/health")
    if "_error" in health:
        _die(f"control-plane inacessível em {BASE}: {health}")
    print(f"  status        : {health.get('status')}")
    print(f"  agents        : {health.get('agents_connected')}")
    print(f"  debug_ws_log  : {health.get('debug_ws_log_enabled')}")
    if not health.get("debug_ws_log_enabled"):
        _die(
            "DEBUG_WS_LOG não está ativo no control-plane. "
            'Sobe com: $env:DEBUG_WS_LOG="true"; docker compose up --build -d'
        )
    if health.get("agents_connected", 0) < 1:
        _die("nenhum agent conectado; espera uns segundos e tenta de novo")


def step_clear_log() -> None:
    print("\n== Limpando log do tap ==")
    r = _req("DELETE", "/_debug/ws-log")
    if "_error" in r:
        _die(f"falha limpando /_debug/ws-log: {r}")
    print(f"  frames removidos: {r.get('cleared')}")


def step_dispatch_scan() -> str:
    print(f"\n== Disparando scan PostgreSQL em {AGENT_ID} ==")
    r = _req("POST", f"/scan/{AGENT_ID}", {"connector": "postgresql"})
    if "_error" in r:
        _die(f"falha no dispatch: {r}")
    print(f"  scan_id: {r.get('scan_id')}")
    return r.get("scan_id", "")


def step_wait_for_result(scan_id: str, timeout_s: float = 15.0) -> None:
    print(f"\n== Aguardando scan_result (timeout {timeout_s}s) ==")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        log = _req("GET", "/_debug/ws-log")
        frames = log.get("frames", []) if isinstance(log, dict) else []
        # Procura a resposta do agent pro scan_id
        for f in frames:
            frame = f.get("frame", {})
            if (f.get("direction") == "in"
                    and frame.get("type") == "scan_result"
                    and frame.get("scan_id") == scan_id):
                print(f"  scan_result chegou após {len(frames)} frames")
                return
        time.sleep(0.5)
    _die(f"timeout sem ver scan_result para {scan_id}")


def step_fetch_frames() -> list[dict]:
    r = _req("GET", "/_debug/ws-log")
    return r.get("frames", []) if isinstance(r, dict) else []


def step_search_leaks(frames: list[dict]) -> list[dict]:
    leaks: list[dict] = []
    for i, f in enumerate(frames):
        payload = json.dumps(f.get("frame", {}), ensure_ascii=False)
        payload_lower = payload.lower()
        for token in SENSITIVE_TOKENS:
            if token in payload:
                leaks.append({
                    "frame_idx": i,
                    "type": "credential_token",
                    "match": token,
                    "direction": f.get("direction"),
                    "frame_type": f.get("frame", {}).get("type"),
                })
        for kw in SENSITIVE_KEYWORDS:
            if kw.lower() in payload_lower:
                leaks.append({
                    "frame_idx": i,
                    "type": "sensitive_keyword",
                    "match": kw,
                    "direction": f.get("direction"),
                    "frame_type": f.get("frame", {}).get("type"),
                })
    return leaks


# ── Relatório ────────────────────────────────────────────────────────────────

def write_report(frames: list[dict], leaks: list[dict], scan_id: str) -> None:
    verdict = "PASS" if not leaks else "FAIL"
    out: list[str] = []
    out.append("# Verificação de segurança — credenciais no WebSocket")
    out.append("")
    out.append(f"- **Data**: {datetime.now().isoformat(timespec='seconds')}")
    out.append(f"- **Control plane**: `{BASE}`")
    out.append(f"- **Agent alvo**: `{AGENT_ID}`")
    out.append(f"- **Scan ID**: `{scan_id}`")
    out.append(f"- **Frames analisados**: {len(frames)}")
    out.append(f"- **Tokens de credencial procurados**: {len(SENSITIVE_TOKENS)}")
    out.append(f"- **Palavras-chave sensíveis procuradas**: {len(SENSITIVE_KEYWORDS)}")
    out.append(f"- **Veredito**: **{verdict}**")
    out.append("")
    out.append("## Metodologia")
    out.append("")
    out.append("1. Control-plane sobe com `DEBUG_WS_LOG=true`, ativando um tap em")
    out.append("   memória que captura cada frame WS (in/out) com timestamp e payload.")
    out.append("2. Script limpa o log, dispara um scan PostgreSQL e espera o")
    out.append("   `scan_result` voltar — ou seja, o ciclo completo foi capturado.")
    out.append("3. Cada frame é serializado em JSON e inspecionado por substring")
    out.append("   match contra uma lista de tokens (credenciais do DSN default)")
    out.append("   e palavras-chave sensíveis (`password`, `POSTGRES_DSN`, etc.).")
    out.append("4. Se qualquer match → **FAIL**. Nenhum match → **PASS**.")
    out.append("")
    out.append("## Tokens procurados")
    out.append("")
    out.append("**Fragmentos de credencial** (matches são fatais):")
    out.append("")
    for t in SENSITIVE_TOKENS:
        out.append(f"- `{t}`")
    out.append("")
    out.append("**Palavras-chave sensíveis** (matches são fatais):")
    out.append("")
    for kw in SENSITIVE_KEYWORDS:
        out.append(f"- `{kw}`")
    out.append("")

    # Tabela de frames
    out.append("## Frames capturados")
    out.append("")
    out.append("| # | direção | tipo | tamanho | sample (primeiros 100 chars) |")
    out.append("|---|---------|------|---------|------------------------------|")
    for i, f in enumerate(frames):
        frame = f.get("frame", {})
        ftype = frame.get("type", "?")
        raw = json.dumps(frame, ensure_ascii=False)
        sample = raw[:100].replace("|", r"\|").replace("\n", " ")
        if len(raw) > 100:
            sample += "…"
        out.append(f"| {i} | `{f.get('direction')}` | `{ftype}` | {len(raw)}B | `{sample}` |")
    out.append("")

    # Leaks (se houver)
    out.append("## Leaks detectados")
    out.append("")
    if not leaks:
        out.append("**Nenhum.** Nenhuma das credenciais conhecidas nem palavras-chave")
        out.append("sensíveis apareceram em qualquer frame WebSocket capturado.")
        out.append("")
        out.append("Isso confirma a propriedade arquitetural central do agent:")
        out.append("**credenciais vivem só no ambiente do cliente e nunca trafegam")
        out.append("para o Radar Cloud**.")
    else:
        out.append("| frame # | direção | tipo | match | categoria |")
        out.append("|---------|---------|------|-------|-----------|")
        for leak in leaks:
            out.append(
                f"| {leak['frame_idx']} | `{leak['direction']}` | "
                f"`{leak['frame_type']}` | `{leak['match']}` | {leak['type']} |"
            )
        out.append("")
        out.append("> Um ou mais fragmentos sensíveis foram encontrados no WS.")
        out.append("> Isso invalida o argumento 'credencial não sai do cliente' —")
        out.append("> investigue o frame referenciado e corrija a origem do leak.")
    out.append("")
    out.append("## Como reproduzir")
    out.append("")
    out.append("```powershell")
    out.append('$env:DEBUG_WS_LOG="true"')
    out.append("docker compose down -v")
    out.append("docker compose up --build -d")
    out.append("Start-Sleep -Seconds 15")
    out.append("python tests/security/verify_no_credential_leak.py")
    out.append("```")
    out.append("")
    out.append("---")
    out.append(f"_Gerado por_ `tests/security/verify_no_credential_leak.py`")

    REPORT_PATH.write_text("\n".join(out), encoding="utf-8")
    print(f"\nRelatório salvo: {REPORT_PATH}")


# ── Entry ────────────────────────────────────────────────────────────────────

def main() -> int:
    step_precheck()
    step_clear_log()
    scan_id = step_dispatch_scan()
    step_wait_for_result(scan_id)
    time.sleep(1.0)  # garante que o scan_ack também foi capturado
    frames = step_fetch_frames()
    leaks = step_search_leaks(frames)
    write_report(frames, leaks, scan_id)

    if leaks:
        print(f"\n[FAIL] {len(leaks)} leak(s) detectado(s). Ver report.md")
        return 1
    print(f"\n[PASS] {len(frames)} frames analisados, zero leaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
