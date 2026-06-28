"""SiteIQ CV sidecar.

Reads camera frames, runs YOLO, applies the calibration homography
(pixel -> site meters), debounces detections into discrete events, and POSTs
them to the local agent's ingest endpoint. The agent owns the durable outbox
and server upload; the sidecar only produces events, so it can crash/restart
without losing buffered data.

Mirrors the model + COCO->construction remap of backend/vision/detector.py.

Usage:
    python sidecar.py --source rtsp://cam/stream --agent http://127.0.0.1:9099
    python sidecar.py --source demo            # use bundled demo mp4s
    python sidecar.py --source 0               # USB camera index 0
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
import uuid
from datetime import datetime, timezone

import requests

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    from ultralytics import YOLO  # type: ignore
    _CV_AVAILABLE = True
except Exception:  # pragma: no cover - sidecar can run in synthetic mode
    _CV_AVAILABLE = False


# COCO -> construction labels (matches VideoDetector.CLASS_REMAP).
CLASS_REMAP = {
    "person": ("worker", "worker"),
    "truck": ("equipment", "truck"),
    "car": ("equipment", "vehicle"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_homography(path: str | None):
    """Load a 3x3 pixel->meter homography from JSON, or None for pass-through.
    The server pushes this via GET /api/ingest/config; the agent persists it."""
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    h = data.get("homography") or data.get("calibration", {}).get("homography")
    if h and _CV_AVAILABLE:
        return np.array(h, dtype="float64").reshape(3, 3)
    return None


def pixel_to_meters(homography, x: float, y: float) -> tuple[float, float]:
    if homography is None:
        return x, y
    pt = np.array([x, y, 1.0])
    out = homography @ pt
    return float(out[0] / out[2]), float(out[1] / out[2])


def post_events(agent_url: str, events: list[dict]) -> None:
    if not events:
        return
    try:
        requests.post(f"{agent_url}/local/events", json=events, timeout=5)
    except Exception as exc:  # the agent may be briefly down; just log
        print(f"[sidecar] post failed: {exc}")


def frame_sources(source: str):
    """Yield (name, cv2.VideoCapture) for the requested source."""
    if source == "demo":
        # The three bundled demo videos in the backend (gitignored).
        here = os.path.dirname(__file__)
        videos = sorted(glob.glob(os.path.join(here, "..", "..", "backend", "vision", "videos", "*.mp4")))
        for v in videos:
            yield os.path.basename(v), cv2.VideoCapture(v)
        return
    if source.isdigit():
        yield f"usb-{source}", cv2.VideoCapture(int(source))
        return
    yield "stream", cv2.VideoCapture(source)


def run(args) -> None:
    if not _CV_AVAILABLE:
        print("[sidecar] ultralytics/opencv not installed; nothing to do. "
              "Install requirements.txt to run inference.")
        return

    homography = load_homography(args.calibration)
    model = YOLO(args.model)
    interval = 1.0 / max(args.fps, 0.1)
    # Per-track debounce: only emit a position when it moved enough or enough
    # time elapsed, so we ship discrete events, not per-frame spam.
    last_emit: dict[str, tuple[float, float, float]] = {}
    # Tracking (stable ids across frames) needs the `lap`/`lapx` assignment
    # solver. If it's missing we fall back to plain detection — still a valid
    # pipeline, just with per-frame ids instead of persistent tracks.
    use_track = True

    for name, cap in frame_sources(args.source):
        if not cap or not cap.isOpened():
            print(f"[sidecar] cannot open source {name}")
            continue
        print(f"[sidecar] processing {name}")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            try:
                if use_track:
                    results = model.track(frame, persist=True, conf=args.conf, verbose=False)
                else:
                    results = model.predict(frame, conf=args.conf, verbose=False)
            except Exception as exc:
                if use_track:
                    print(f"[sidecar] tracking unavailable ({exc}); falling back to detection")
                    use_track = False
                    results = model.predict(frame, conf=args.conf, verbose=False)
                else:
                    raise
            events: list[dict] = []
            for r in results:
                boxes = getattr(r, "boxes", None)
                if boxes is None:
                    continue
                for b in boxes:
                    cls_name = model.names.get(int(b.cls[0]), "")
                    mapped = CLASS_REMAP.get(cls_name)
                    if not mapped:
                        continue
                    subject_type, subtype = mapped
                    x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                    # Bottom-center of the box is the ground contact point.
                    px, py = (x1 + x2) / 2.0, y2
                    if use_track and b.id is not None:
                        subject_id = f"{subtype}-{int(b.id[0])}"
                    else:
                        # Detection-only fallback: bucket by a coarse position
                        # grid so the same spot maps to a stable-ish subject.
                        subject_id = f"{subtype}-g{int(px // 40)}_{int(py // 40)}"
                    mx, my = pixel_to_meters(homography, px, py)
                    conf = float(b.conf[0])

                    now = time.time()
                    prev = last_emit.get(subject_id)
                    moved = prev is None or ((mx - prev[1]) ** 2 + (my - prev[2]) ** 2) ** 0.5 > 1.0
                    stale = prev is None or (now - prev[0]) > 5.0
                    if not (moved or stale):
                        continue
                    last_emit[subject_id] = (now, mx, my)
                    events.append({
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                        "kind": "worker.position" if subject_type == "worker" else "equipment.position",
                        "client_event_id": uuid.uuid4().hex,
                        "occurred_at": _now_iso(),
                        "payload": {"x": round(mx, 2), "y": round(my, 2), "subtype": subtype},
                        "confidence": round(conf, 3),
                        "source": "camera",
                    })
            post_events(args.agent, events)
            time.sleep(interval)
        cap.release()


def main() -> None:
    p = argparse.ArgumentParser(description="SiteIQ CV sidecar")
    p.add_argument("--source", default="demo", help="rtsp url | usb index | path | 'demo'")
    p.add_argument("--agent", default="http://127.0.0.1:9099", help="local agent ingest base URL")
    p.add_argument("--model", default="yolov8n.pt")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--fps", type=float, default=2.0, help="frames processed per second")
    p.add_argument("--calibration", default=os.getenv("SITEIQ_CALIBRATION", ""))
    run(p.parse_args())


if __name__ == "__main__":
    main()
