import cv2
import base64
import glob
import os
import time
from ultralytics import YOLO

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "videos")
MODEL_PATH = "yolov8n.pt"

CONSTRUCTION_CLASSES = {
    0: "person",       # worker
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    24: "backpack",
    25: "umbrella",
    56: "chair",
    63: "laptop",
}

CLASS_REMAP = {
    "person": "Worker",
    "truck": "Truck",
    "car": "Vehicle",
    "bus": "Vehicle",
    "motorcycle": "Vehicle",
    "bicycle": "Bicycle",
    "backpack": "Equipment",
    "umbrella": "Canopy",
    "chair": "Furniture",
}


class VideoDetector:
    def __init__(self):
        self.model = YOLO(MODEL_PATH)
        self.videos = self._find_videos()
        self.caps: dict[str, cv2.VideoCapture] = {}
        self.frame_idx: dict[str, int] = {}

        for vid_id, path in self.videos.items():
            cap = cv2.VideoCapture(path)
            self.caps[vid_id] = cap
            self.frame_idx[vid_id] = 0

    def _find_videos(self) -> dict[str, str]:
        videos = {}
        if not os.path.exists(VIDEOS_DIR):
            return videos
        for f in sorted(glob.glob(os.path.join(VIDEOS_DIR, "*.mp4"))):
            name = os.path.splitext(os.path.basename(f))[0]
            videos[name] = f
        return videos

    def get_video_ids(self) -> list[str]:
        return list(self.videos.keys())

    def get_video_info(self, vid_id: str) -> dict | None:
        cap = self.caps.get(vid_id)
        if not cap:
            return None
        return {
            "id": vid_id,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }

    def get_next_frame(self, vid_id: str, skip: int = 3) -> dict | None:
        """Read next frame, run YOLO, return base64 JPEG + detections."""
        cap = self.caps.get(vid_id)
        if not cap:
            return None

        # Advance by skip frames for performance
        idx = self.frame_idx.get(vid_id, 0)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        idx = (idx + skip) % max(total, 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        self.frame_idx[vid_id] = idx

        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.frame_idx[vid_id] = 0
            ret, frame = cap.read()
            if not ret:
                return None

        # Resize for faster inference
        h, w = frame.shape[:2]
        max_dim = 640
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        t0 = time.time()
        results = self.model(frame, verbose=False, conf=0.20)[0]
        inference_ms = (time.time() - t0) * 1000

        fh, fw = frame.shape[:2]
        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            name = self.model.names[cls_id]
            label = CLASS_REMAP.get(name, name.capitalize())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]

            detections.append({
                "class": label,
                "confidence": round(conf, 2),
                "bbox": [round(x1 / fw, 4), round(y1 / fh, 4),
                         round(x2 / fw, 4), round(y2 / fh, 4)],
            })

        # Encode frame as JPEG
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        b64 = base64.b64encode(jpeg.tobytes()).decode('ascii')

        return {
            "video_id": vid_id,
            "frame_idx": idx,
            "width": fw,
            "height": fh,
            "detections": detections,
            "inference_ms": round(inference_ms, 1),
            "image": b64,
        }

    def cleanup(self):
        for cap in self.caps.values():
            cap.release()
