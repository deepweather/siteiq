import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from config import WS_PUSH_INTERVAL

router = APIRouter()

_engine = None
_get_analytics = None


def init_ws(engine, get_analytics_fn):
    global _engine, _get_analytics
    _engine = engine
    _get_analytics = get_analytics_fn


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            snapshot = _engine.get_state_snapshot()
            analytics = _get_analytics()

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
        pass
    except Exception:
        pass
