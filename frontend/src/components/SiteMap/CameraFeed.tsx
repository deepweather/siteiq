import { useRef, useEffect, useState } from 'react';
import { WS_BASE } from '../../services/api';

interface Detection {
  class: string;
  confidence: number;
  bbox: [number, number, number, number]; // normalized x1,y1,x2,y2
}

interface FrameData {
  video_id: string;
  frame_idx: number;
  width: number;
  height: number;
  detections: Detection[];
  inference_ms: number;
  image: string; // base64 JPEG
}

interface CameraFeedProps {
  videoId: string;
  label: string;
}

const BOX_COLORS: Record<string, string> = {
  Worker: '#22c55e',
  Truck: '#f59e0b',
  Vehicle: '#3b82f6',
  Equipment: '#a855f7',
};

export function CameraFeed({ videoId, label }: CameraFeedProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [connected, setConnected] = useState(false);
  // Stats live in refs (read by the draw RAF loop) so they don't re-trigger
  // the draw effect. Previously these were state and caused the RAF loop
  // to tear down and recreate 5×/sec, producing visible flicker.
  const detectionCountRef = useRef(0);
  const inferenceMsRef = useRef(0);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const frameRef = useRef<FrameData | null>(null);

  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectDelay = 1000;
    let reconnectTimer: number | null = null;
    const img = new Image();
    imgRef.current = img;

    const connect = () => {
      if (cancelled) return;
      ws = new WebSocket(`${WS_BASE}/ws/camera/${videoId}`);

      ws.onopen = () => {
        setConnected(true);
        reconnectDelay = 1000;
      };

      ws.onclose = () => {
        setConnected(false);
        if (cancelled) return;
        reconnectTimer = window.setTimeout(() => {
          reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
          connect();
        }, reconnectDelay);
      };

      ws.onerror = () => {
        ws?.close();
      };

      ws.onmessage = (event) => {
        const data: FrameData = JSON.parse(event.data);
        frameRef.current = data;
        detectionCountRef.current = data.detections.length;
        inferenceMsRef.current = data.inference_ms;
        img.src = `data:image/jpeg;base64,${data.image}`;
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [videoId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf: number;
    const draw = () => {
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cw = rect.width;
      const ch = rect.height;

      // Draw video frame
      const img = imgRef.current;
      const frame = frameRef.current;
      if (img && img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, 0, 0, cw, ch);
      } else {
        ctx.fillStyle = '#111';
        ctx.fillRect(0, 0, cw, ch);
      }

      // Draw detections
      if (frame) {
        for (const det of frame.detections) {
          const [nx1, ny1, nx2, ny2] = det.bbox;
          const x1 = nx1 * cw;
          const y1 = ny1 * ch;
          const x2 = nx2 * cw;
          const y2 = ny2 * ch;
          const bw = x2 - x1;
          const bh = y2 - y1;

          const color = BOX_COLORS[det.class] || '#ef4444';

          // Bounding box
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.strokeRect(x1, y1, bw, bh);

          // Corner brackets
          const cl = Math.min(8, bw * 0.3);
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.moveTo(x1, y1 + cl); ctx.lineTo(x1, y1); ctx.lineTo(x1 + cl, y1);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(x2 - cl, y1); ctx.lineTo(x2, y1); ctx.lineTo(x2, y1 + cl);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(x1, y2 - cl); ctx.lineTo(x1, y2); ctx.lineTo(x1 + cl, y2);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(x2 - cl, y2); ctx.lineTo(x2, y2); ctx.lineTo(x2, y2 - cl);
          ctx.stroke();

          // Label
          const labelText = `${det.class} ${(det.confidence * 100).toFixed(0)}%`;
          ctx.font = 'bold 10px JetBrains Mono, monospace';
          const tw = ctx.measureText(labelText).width;
          ctx.fillStyle = color;
          ctx.fillRect(x1, y1 - 14, tw + 6, 14);
          ctx.fillStyle = '#000';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(labelText, x1 + 3, y1 - 13);
        }
      }

      // HUD overlay
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillRect(0, 0, cw, 16);
      ctx.fillRect(0, ch - 14, cw, 14);

      ctx.font = 'bold 9px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillStyle = connected ? '#ef4444' : '#666';
      ctx.fillText(connected ? '● REC' : '● OFF', 4, 3);
      ctx.fillStyle = '#fff';
      ctx.fillText(label, 40, 3);

      const now = new Date();
      ctx.textAlign = 'right';
      ctx.fillText(`${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`, cw - 4, 3);

      ctx.textBaseline = 'bottom';
      ctx.textAlign = 'left';
      ctx.fillStyle = '#22c55e';
      ctx.fillText(`${detectionCountRef.current} objects`, 4, ch - 2);
      ctx.fillStyle = '#888';
      ctx.textAlign = 'center';
      ctx.fillText('YOLOv8 · SiteIQ Vision', cw / 2, ch - 2);
      ctx.textAlign = 'right';
      ctx.fillText(`${inferenceMsRef.current.toFixed(0)}ms`, cw - 4, ch - 2);

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => cancelAnimationFrame(raf);
  }, [connected, label]);

  return (
    <div ref={containerRef} className="flex-1 relative bg-black min-h-[120px]">
      <canvas ref={canvasRef} className="absolute inset-0" />
      {!connected && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs text-zinc-500">Connecting to {videoId}...</span>
        </div>
      )}
    </div>
  );
}
