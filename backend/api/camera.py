import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_detector = None


def init_camera(detector):
    global _detector
    _detector = detector


@router.get("/api/cameras")
async def list_cameras():
    if not _detector:
        return []
    result = []
    for vid_id in _detector.get_video_ids():
        info = _detector.get_video_info(vid_id)
        if info:
            result.append(info)
    return result


@router.websocket("/ws/camera/{video_id}")
async def camera_feed(websocket: WebSocket, video_id: str):
    """Streams real YOLO detections on video frames at ~5 FPS."""
    await websocket.accept()
    if not _detector or video_id not in _detector.get_video_ids():
        await websocket.close(code=1008, reason="Video not found")
        return

    try:
        while True:
            frame_data = _detector.get_next_frame(video_id, skip=5)
            if frame_data:
                await websocket.send_json(frame_data)
            await asyncio.sleep(0.2)  # ~5 FPS
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
