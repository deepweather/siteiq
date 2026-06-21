"""WebSocket — broadcasts simulation state at 10Hz."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws_auth import authenticate_ws
from config import WS_PUSH_INTERVAL
from simulation.engine import SimulationEngine

router = APIRouter()
logger = logging.getLogger("siteiq.api.ws")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """10Hz simulation-state stream, scoped to the user's active org.

    FastAPI's Depends() works for WebSockets but is awkward — we read
    `app.state.registry` directly and look up by org_id from the
    authenticated session.
    """
    registry = getattr(websocket.app.state, "registry", None)
    if registry is None:
        await websocket.close(code=1011, reason="State source not ready")
        return
    org_id = await authenticate_ws(websocket)
    if org_id is None:
        return
    source = registry.for_org(org_id)
    await websocket.accept()
    try:
        while True:
            if isinstance(source, SimulationEngine):
                snapshot = source.get_state_snapshot()
            else:
                snapshot = {
                    "sim_time": source.sim_time,
                    "sim_day": source.sim_day,
                    "assets": [a.to_broadcast_dict() for a in source.assets],
                    "trails": {},
                }
            analytics = registry.latest_analytics_for(org_id)
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
        logger.exception("state_ws_error", extra={"org_id": org_id})
