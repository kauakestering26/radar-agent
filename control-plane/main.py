"""
Radar Agent POC — Control Plane
Simula o backend do Radar Cloud que:
 - Registra agents que se conectam
 - Envia tasks de scan via WebSocket
 - Recebe e armazena os resultados
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CONTROL-PLANE] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Radar Control Plane (POC)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Estado em memória (em produção: PostgreSQL + Redis) ───────────────────────

agents: dict[str, dict] = {}          # agent_id → {ws, info, connected_at}
results: list[dict] = []              # todos os assets descobertos
pending_tasks: dict[str, list] = {}   # agent_id → [task, ...]


# ── WS Tap opcional (APENAS pra verificação de segurança em POC) ─────────────
#
# Quando DEBUG_WS_LOG=true, o control-plane guarda em memória cada frame trocado
# com os agents (direção, agent_id, payload, timestamp) e expõe endpoints
# /_debug/ws-log. O script tests/security/verify_no_credential_leak.py usa isso
# pra provar empiricamente que nenhuma credencial trafega no WebSocket.
#
# Em produção a env var é desligada → os endpoints retornam 404 e o log fica
# vazio. Nenhum byte a mais circula.

DEBUG_WS_LOG: bool = os.getenv("DEBUG_WS_LOG", "").lower() in ("1", "true", "yes", "on")
ws_log: list[dict] = []
WS_LOG_MAX = 1000  # ring buffer


def _tap(direction: str, agent_id: str, frame: dict) -> None:
    """direction: 'in' (agent→CP) ou 'out' (CP→agent)."""
    if not DEBUG_WS_LOG:
        return
    ws_log.append({
        "ts": datetime.utcnow().isoformat(),
        "direction": direction,
        "agent_id": agent_id,
        "frame": frame,
    })
    # cap o buffer pra evitar consumo descontrolado de memória
    if len(ws_log) > WS_LOG_MAX:
        del ws_log[: len(ws_log) - WS_LOG_MAX]


async def _send_json_tapped(ws: WebSocket, agent_id: str, payload: dict) -> None:
    """Wrapper que loga o frame ANTES de enviar. Usar em vez de ws.send_json."""
    _tap("out", agent_id, payload)
    await ws.send_json(payload)


# ── WebSocket: canal principal agent <-> control plane ───────────────────────

@app.websocket("/ws/agent/{agent_id}")
async def agent_ws(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    log.info(f"Agent conectado: {agent_id}")

    agents[agent_id] = {
        "ws": websocket,
        "connected_at": datetime.utcnow().isoformat(),
        "status": "idle",
        "last_seen": datetime.utcnow().isoformat(),
    }

    # Mensagem de boas-vindas
    await _send_json_tapped(websocket, agent_id, {
        "type": "welcome",
        "agent_id": agent_id,
        "message": "Conectado ao Radar Control Plane",
    })

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            _tap("in", agent_id, msg)
            await handle_agent_message(agent_id, msg)

    except WebSocketDisconnect:
        log.info(f"Agent desconectado: {agent_id}")
        agents.pop(agent_id, None)


async def handle_agent_message(agent_id: str, msg: dict):
    """Processa mensagens recebidas dos agents."""
    msg_type = msg.get("type")
    log.info(f"[{agent_id}] Mensagem recebida: {msg_type}")

    if msg_type == "heartbeat":
        agents[agent_id]["last_seen"] = datetime.utcnow().isoformat()
        agents[agent_id]["status"] = "idle"
        ws = agents[agent_id]["ws"]
        await _send_json_tapped(ws, agent_id, {"type": "heartbeat_ack"})

    elif msg_type == "scan_result":
        # Agent devolveu assets descobertos
        assets = msg.get("assets", [])
        scan_id = msg.get("scan_id")
        log.info(f"[{agent_id}] Recebidos {len(assets)} assets do scan {scan_id}")
        for asset in assets:
            asset["agent_id"] = agent_id
            asset["scan_id"] = scan_id
            asset["received_at"] = datetime.utcnow().isoformat()
            results.append(asset)
        agents[agent_id]["status"] = "idle"
        ws = agents[agent_id]["ws"]
        await _send_json_tapped(ws, agent_id, {
            "type": "scan_ack",
            "scan_id": scan_id,
            "assets_received": len(assets),
        })

    elif msg_type == "scan_error":
        log.error(f"[{agent_id}] Erro no scan: {msg.get('error')}")
        agents[agent_id]["status"] = "idle"

    else:
        log.warning(f"[{agent_id}] Tipo de mensagem desconhecido: {msg_type}")


# ── REST API: dashboard e disparo de scans ───────────────────────────────────

@app.get("/agents")
def list_agents():
    """Lista todos os agents conectados."""
    return [
        {
            "agent_id": aid,
            "connected_at": info["connected_at"],
            "last_seen": info["last_seen"],
            "status": info["status"],
        }
        for aid, info in agents.items()
    ]


@app.post("/scan/{agent_id}")
async def dispatch_scan(agent_id: str, payload: dict[str, Any] = {}):
    """
    Dispara um scan em um agent específico.
    Body (opcional): { "connector": "postgresql", "config": {...} }
    """
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' não encontrado ou desconectado")

    scan_id = str(uuid.uuid4())[:8]
    task = {
        "type": "scan_task",
        "scan_id": scan_id,
        "connector": payload.get("connector", "mock"),
        "config": payload.get("config", {}),
    }

    ws = agents[agent_id]["ws"]
    agents[agent_id]["status"] = "scanning"
    await _send_json_tapped(ws, agent_id, task)
    log.info(f"Scan {scan_id} disparado para agent {agent_id} (conector: {task['connector']})")

    return {"scan_id": scan_id, "agent_id": agent_id, "status": "dispatched"}


@app.post("/scan-all")
async def scan_all(payload: dict[str, Any] = {}):
    """Dispara scan em todos os agents conectados."""
    if not agents:
        raise HTTPException(status_code=404, detail="Nenhum agent conectado")

    dispatched = []
    for agent_id in list(agents.keys()):
        r = await dispatch_scan(agent_id, payload)
        dispatched.append(r)
    return dispatched


@app.get("/results")
def get_results(agent_id: str = None, connector: str = None):
    """Lista todos os assets descobertos, com filtros opcionais."""
    filtered = results
    if agent_id:
        filtered = [r for r in filtered if r.get("agent_id") == agent_id]
    if connector:
        filtered = [r for r in filtered if r.get("connector") == connector]
    return {
        "total": len(filtered),
        "assets": filtered,
    }


@app.delete("/results")
def clear_results():
    results.clear()
    return {"message": "Resultados limpos"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Dashboard HTML servido na raiz — visualiza agents e assets em tempo real."""
    html_path = Path(__file__).parent / "dashboard.html"
    if not html_path.exists():
        return HTMLResponse("<h1>dashboard.html não encontrado</h1>", status_code=500)
    return FileResponse(html_path, media_type="text/html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agents_connected": len(agents),
        "assets_discovered": len(results),
        "debug_ws_log_enabled": DEBUG_WS_LOG,
    }


# ── Debug endpoints (só existem se DEBUG_WS_LOG=true) ────────────────────────

@app.get("/_debug/ws-log")
def debug_ws_log():
    """Retorna o log de frames WS capturados. 404 se DEBUG_WS_LOG desligado."""
    if not DEBUG_WS_LOG:
        raise HTTPException(status_code=404, detail="WS log disabled")
    return {"enabled": True, "count": len(ws_log), "frames": ws_log}


@app.delete("/_debug/ws-log")
def debug_ws_log_clear():
    """Limpa o log. 404 se DEBUG_WS_LOG desligado."""
    if not DEBUG_WS_LOG:
        raise HTTPException(status_code=404, detail="WS log disabled")
    n = len(ws_log)
    ws_log.clear()
    return {"cleared": n}
