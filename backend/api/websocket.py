"""WebSocket — broadcasts simulation state at 10Hz."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import WS_PUSH_INTERVAL
from simulation.engine import SimulationEngine

router = APIRouter()
logger = logging.getLogger("siteiq.api.ws")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # FastAPI's Depends() works for WebSockets but is awkward — using
    # app.state directly keeps the dependency surface explicit and lets us
    # short-circuit cleanly if the source isn't ready.
    source = getattr(websocket.app.state, "source", None)
    if source is None:
        await websocket.close(code=1011, reason="State source not ready")
        return
    await websocket.accept()
    try:
        while True:
            if isinstance(source, SimulationEngine):
                snapshot = source.get_state_snapshot()
            else:
                # Generic Protocol-only path (a LiveSource would land here)
                snapshot = {
                    "sim_time": source.sim_time,
                    "sim_day": source.sim_day,
                    "assets": [a.to_broadcast_dict() for a in source.assets],
                    "trails": {},
                }
            analytics = getattr(websocket.app.state, "latest_analytics", None)
            payload = {
                "type": "state_update",
                "sim_time": snapshot["sim_time"],
                "sim_day": snapshot["sim_day"],
                "assets": snapshot["assets"],
                "trails": snapshot["trails"],
                "analytics": analytics.model_dump() if analytics else None,
            }
            await websocket.send_json(payload)
            await asyncio.sleep(WS_PUSH_INTERVAL)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("state_ws_error")
