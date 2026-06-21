"""Camera streaming endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.deps import get_current_org, get_detector
from api.ws_auth import authenticate_ws
from db.models import Org
from vision.detector import VideoDetector

router = APIRouter()
logger = logging.getLogger("siteiq.api.camera")


@router.get("/api/cameras")
async def list_cameras(
    detector: VideoDetector = Depends(get_detector),
    _: Org = Depends(get_current_org),
):
    result = []
    for vid_id in detector.get_video_ids():
        info = detector.get_video_info(vid_id)
        if info:
            result.append(info)
    return result


@router.websocket("/ws/camera/{video_id}")
async def camera_feed(websocket: WebSocket, video_id: str):
    """Streams real YOLO detections on video frames at ~5 FPS."""
    detector = getattr(websocket.app.state, "detector", None)
    if detector is None or video_id not in detector.get_video_ids():
        await websocket.close(code=1008, reason="Detector or video not available")
        return
    if await authenticate_ws(websocket) is None:
        return
    await websocket.accept()
    try:
        while True:
            # Run synchronous OpenCV + YOLO work off the event loop so it
            # doesn't stall the sim WebSocket and other REST endpoints.
            frame_data = await asyncio.to_thread(
                detector.get_next_frame, video_id, 5
            )
            if frame_data:
                await websocket.send_json(frame_data)
            await asyncio.sleep(0.2)  # ~5 FPS
    except WebSocketDisconnect:
        # Normal client disconnect — not an error
        return
    except Exception:
        logger.exception(
            "camera_stream_error",
            extra={"video_id": video_id},
        )
