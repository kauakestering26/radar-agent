"""
Radar Agent POC
Roda na máquina do cliente. Responsabilidades:
 - Conecta ao Control Plane via WebSocket (outbound only)
 - Recebe tasks de scan
 - Executa o scanner localmente (credenciais nunca saem daqui)
 - Devolve apenas os resultados (assets descobertos)
"""

import asyncio
import json
import logging
import os
import socket
import uuid

import websockets

from connectors import mock_scanner, postgresql

logging.basicConfig(level=logging.INFO, format="%(asctime)s [AGENT] %(message)s")
log = logging.getLogger(__name__)

# ── Configuração via env vars ─────────────────────────────────────────────────

CONTROL_PLANE_URL = os.getenv("CONTROL_PLANE_URL", "ws://control-plane:8000")
AGENT_ID = os.getenv("AGENT_ID", f"agent-{socket.gethostname()}-{str(uuid.uuid4())[:4]}")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))  # segundos

# Mapa de conectores disponíveis neste agent.
# Credenciais vivem em env vars dentro deste agent — nunca vêm via WebSocket.
CONNECTORS = {
    "mock":       mock_scanner,
    "postgresql": postgresql,
    # "github":     github_scanner,
    # "kubernetes": kubernetes_scanner,
}


# ── Loop principal ────────────────────────────────────────────────────────────

async def connect_and_run():
    ws_url = f"{CONTROL_PLANE_URL}/ws/agent/{AGENT_ID}"
    log.info(f"Conectando ao Control Plane: {ws_url}")

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                log.info(f"Conectado! Agent ID: {AGENT_ID}")

                # Inicia heartbeat em paralelo
                heartbeat_task = asyncio.create_task(send_heartbeats(ws))

                try:
                    await listen(ws)
                finally:
                    heartbeat_task.cancel()

        except (ConnectionRefusedError, websockets.exceptions.ConnectionClosed, OSError) as e:
            log.warning(f"Conexão perdida: {e}. Reconectando em 5s...")
            await asyncio.sleep(5)


async def listen(ws):
    """Aguarda e processa mensagens do Control Plane."""
    async for raw in ws:
        msg = json.loads(raw)
        msg_type = msg.get("type")

        if msg_type == "welcome":
            log.info(f"Control Plane: {msg.get('message')}")

        elif msg_type == "heartbeat_ack":
            log.debug("Heartbeat confirmado")

        elif msg_type == "scan_task":
            asyncio.create_task(execute_scan(ws, msg))

        else:
            log.warning(f"Mensagem desconhecida: {msg_type}")


async def execute_scan(ws, task: dict):
    """Executa o scan e envia os resultados de volta."""
    scan_id = task.get("scan_id")
    connector_name = task.get("connector", "mock")
    config = task.get("config", {})

    log.info(f"Iniciando scan {scan_id} — conector: {connector_name}")

    scanner = CONNECTORS.get(connector_name)
    if not scanner:
        await ws.send(json.dumps({
            "type": "scan_error",
            "scan_id": scan_id,
            "error": f"Conector '{connector_name}' não disponível neste agent",
        }))
        return

    try:
        assets = await scanner.scan(config)
        log.info(f"Scan {scan_id} concluído — {len(assets)} assets encontrados")

        await ws.send(json.dumps({
            "type": "scan_result",
            "scan_id": scan_id,
            "connector": connector_name,
            "assets": assets,
        }))

    except Exception as e:
        log.error(f"Erro no scan {scan_id}: {e}")
        await ws.send(json.dumps({
            "type": "scan_error",
            "scan_id": scan_id,
            "error": str(e),
        }))


async def send_heartbeats(ws):
    """Envia heartbeat periódico para manter a conexão viva."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await ws.send(json.dumps({"type": "heartbeat", "agent_id": AGENT_ID}))
            log.debug("Heartbeat enviado")
        except Exception:
            break


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(connect_and_run())

