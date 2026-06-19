import { useRef, useEffect } from 'react';
import type { AssetUpdate } from '../../types/assets';
import { TRADE_COLORS } from '../../utils/colors';

interface CameraFeedProps {
  assetsRef: React.MutableRefObject<AssetUpdate[]>;
  cameraId: number;
}

const CAMERA_CONFIGS = [
  { id: 1, label: 'CAM 1 — North', viewX: 0, viewY: 0, viewW: 140, viewH: 90, angle: 'NW Corner' },
  { id: 2, label: 'CAM 2 — South', viewX: 50, viewY: 70, viewW: 160, viewH: 95, angle: 'SE Corner' },
  { id: 3, label: 'CAM 3 — Gate', viewX: 80, viewY: 120, viewW: 80, viewH: 45, angle: 'Gate Area' },
];

const CLASS_LABELS: Record<string, string> = {
  structural: 'Worker:Structural',
  mep: 'Worker:MEP',
  finishing: 'Worker:Finishing',
  general: 'Worker:General',
  tower_crane: 'Crane',
  concrete_pump: 'Pump',
  excavator: 'Excavator',
  toilet: 'Facility:WC',
  breakroom: 'Facility:Break',
  office: 'Facility:Office',
  toolcrib: 'Facility:Tools',
  rebar: 'Material:Rebar',
  conduit: 'Material:Conduit',
  drywall: 'Material:Drywall',
  concrete: 'Material:Concrete',
};

const BOX_COLORS: Record<string, string> = {
  worker: '#22c55e',
  equipment: '#f59e0b',
  facility: '#3b82f6',
  material: '#a855f7',
};

export function CameraFeed({ assetsRef, cameraId }: CameraFeedProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cam = CAMERA_CONFIGS[cameraId % CAMERA_CONFIGS.length];

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(container);

    let raf: number;
    const loop = () => {
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cw = canvas.width / dpr;
      const ch = canvas.height / dpr;

      // Dark camera background with noise
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(0, 0, cw, ch);

      // Simulated camera perspective — slightly grayed ground
      const scaleX = cw / cam.viewW;
      const scaleY = ch / cam.viewH;

      // Ground plane gradient
      const grad = ctx.createLinearGradient(0, 0, 0, ch);
      grad.addColorStop(0, '#2a2520');
      grad.addColorStop(1, '#1f1d18');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cw, ch);

      // Scan line effect
      ctx.strokeStyle = 'rgba(255,255,255,0.02)';
      ctx.lineWidth = 0.5;
      for (let y = 0; y < ch; y += 3) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(cw, y);
        ctx.stroke();
      }

      // Filter assets in this camera's viewport
      const visible = assetsRef.current.filter(a =>
        a.x >= cam.viewX && a.x <= cam.viewX + cam.viewW &&
        a.y >= cam.viewY && a.y <= cam.viewY + cam.viewH
      );

      let detectionCount = 0;

      for (const a of visible) {
        const sx = (a.x - cam.viewX) * scaleX;
        const sy = (a.y - cam.viewY) * scaleY;
        const boxColor = BOX_COLORS[a.type] || '#888';
        const label = CLASS_LABELS[a.subtype] || a.subtype;
        const confidence = (0.85 + Math.random() * 0.14).toFixed(2);

        let bw: number, bh: number;
        if (a.type === 'worker') {
          bw = 18; bh = 32;
        } else if (a.type === 'equipment') {
          bw = 40; bh = 35;
        } else if (a.type === 'facility') {
          bw = 30; bh = 24;
        } else {
          bw = 22; bh = 16;
        }

        const bx = sx - bw / 2;
        const by = sy - bh / 2;

        // Bounding box
        ctx.strokeStyle = boxColor;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(bx, by, bw, bh);

        // Corner brackets for ML look
        const cornerLen = 5;
        ctx.lineWidth = 2;
        // Top-left
        ctx.beginPath();
        ctx.moveTo(bx, by + cornerLen); ctx.lineTo(bx, by); ctx.lineTo(bx + cornerLen, by);
        ctx.stroke();
        // Top-right
        ctx.beginPath();
        ctx.moveTo(bx + bw - cornerLen, by); ctx.lineTo(bx + bw, by); ctx.lineTo(bx + bw, by + cornerLen);
        ctx.stroke();
        // Bottom-left
        ctx.beginPath();
        ctx.moveTo(bx, by + bh - cornerLen); ctx.lineTo(bx, by + bh); ctx.lineTo(bx + cornerLen, by + bh);
        ctx.stroke();
        // Bottom-right
        ctx.beginPath();
        ctx.moveTo(bx + bw - cornerLen, by + bh); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx + bw, by + bh - cornerLen);
        ctx.stroke();

        // Label background
        const labelText = `${label} ${confidence}`;
        ctx.font = '9px JetBrains Mono, monospace';
        const tw = ctx.measureText(labelText).width;
        ctx.fillStyle = boxColor;
        ctx.fillRect(bx, by - 13, tw + 6, 13);
        ctx.fillStyle = '#000';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(labelText, bx + 3, by - 12);

        detectionCount++;
      }

      // Camera HUD overlay
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(0, 0, cw, 20);
      ctx.fillRect(0, ch - 18, cw, 18);

      ctx.font = 'bold 10px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#ef4444';
      ctx.fillText('● REC', 6, 5);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(cam.label, 48, 5);

      const now = new Date();
      const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
      ctx.textAlign = 'right';
      ctx.fillText(timeStr, cw - 6, 5);

      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = '#22c55e';
      ctx.fillText(`${detectionCount} objects`, 6, ch - 4);
      ctx.fillStyle = '#888';
      ctx.textAlign = 'center';
      ctx.fillText('SiteIQ Vision Pipeline v2.1', cw / 2, ch - 4);
      ctx.textAlign = 'right';
      ctx.fillText(`${(28 + Math.random() * 4).toFixed(1)} FPS`, cw - 6, ch - 4);

      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [assetsRef, cam]);

  return (
    <div ref={containerRef} className="w-full h-full min-h-[120px] bg-black rounded overflow-hidden">
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}

export { CAMERA_CONFIGS };
