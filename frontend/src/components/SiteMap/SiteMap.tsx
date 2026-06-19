import { useRef, useEffect, useState, useCallback } from 'react';
import type { AssetUpdate, Trail } from '../../types/assets';
import type { Zone } from '../../types/site';
import type { Recommendation } from '../../types/analytics';
import { Toggle } from '../common/Toggle';
import { renderFrame } from './renderer';
import { CameraFeed } from './CameraFeed';
import { useEffect } from 'react';

interface SiteMapProps {
  zones: Zone[];
  siteWidth: number;
  siteHeight: number;
  assetsRef: React.MutableRefObject<AssetUpdate[]>;
  trailsRef: React.MutableRefObject<Trail>;
  recommendations: Recommendation[];
  selectedAssetId: string | null;
  onAssetSelect: (id: string | null) => void;
}

export function SiteMap({ zones, siteWidth, siteHeight, assetsRef, trailsRef, recommendations, selectedAssetId, onAssetSelect }: SiteMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef({ w: 0, h: 0 });
  const [showTrails, setShowTrails] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showRecs, setShowRecs] = useState(true);
  const [showCameras, setShowCameras] = useState(false);
  const [cameraIds, setCameraIds] = useState<string[]>([]);

  useEffect(() => {
    if (showCameras && cameraIds.length === 0) {
      fetch('http://localhost:8000/api/cameras')
        .then(r => r.json())
        .then((cams: { id: string }[]) => setCameraIds(cams.map(c => c.id)))
        .catch(() => {});
    }
  }, [showCameras, cameraIds.length]);

  const viewRef = useRef({ zoom: 1, panX: 0, panY: 0 });
  const dragRef = useRef<{ active: boolean; moved: boolean; startX: number; startY: number; startPanX: number; startPanY: number }>({
    active: false, moved: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0,
  });

  const getBaseTransform = useCallback(() => {
    const { w, h } = sizeRef.current;
    if (w === 0 || h === 0) return { scale: 3, offsetX: 20, offsetY: 20 };
    const padX = 30;
    const padY = 30;
    const scaleX = (w - padX * 2) / siteWidth;
    const scaleY = (h - padY * 2) / siteHeight;
    const scale = Math.min(scaleX, scaleY);
    const offsetX = (w - siteWidth * scale) / 2;
    const offsetY = (h - siteHeight * scale) / 2;
    return { scale, offsetX, offsetY };
  }, [siteWidth, siteHeight]);

  const getTransform = useCallback(() => {
    const base = getBaseTransform();
    const v = viewRef.current;
    return {
      scale: base.scale * v.zoom,
      offset: {
        x: base.offsetX * v.zoom + v.panX,
        y: base.offsetY * v.zoom + v.panY,
      },
    };
  }, [getBaseTransform]);

  const screenToSite = useCallback((screenX: number, screenY: number) => {
    const { scale, offset } = getTransform();
    return {
      x: (screenX - offset.x) / scale,
      y: (screenY - offset.y) / scale,
    };
  }, [getTransform]);

  const handleCanvasClick = useCallback((e: MouseEvent) => {
    if (dragRef.current.moved) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const site = screenToSite(clickX, clickY);

    const { scale } = getTransform();
    const hitRadius = 12 / scale;

    let bestId: string | null = null;
    let bestDist = hitRadius;

    for (const a of assetsRef.current) {
      const dx = a.x - site.x;
      const dy = a.y - site.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < bestDist) {
        bestDist = dist;
        bestId = a.id;
      }
    }

    onAssetSelect(bestId);
  }, [screenToSite, getTransform, assetsRef, onAssetSelect]);

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
      sizeRef.current = { w: rect.width, h: rect.height };
    };

    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const v = viewRef.current;
      const zoomFactor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      const newZoom = Math.max(0.5, Math.min(10, v.zoom * zoomFactor));
      const ratio = newZoom / v.zoom;

      v.panX = mouseX - ratio * (mouseX - v.panX);
      v.panY = mouseY - ratio * (mouseY - v.panY);
      v.zoom = newZoom;
    };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      const d = dragRef.current;
      d.active = true;
      d.moved = false;
      d.startX = e.clientX;
      d.startY = e.clientY;
      d.startPanX = viewRef.current.panX;
      d.startPanY = viewRef.current.panY;
      canvas.style.cursor = 'grabbing';
    };

    const onMouseMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (d.active) {
        const dx = e.clientX - d.startX;
        const dy = e.clientY - d.startY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) d.moved = true;
        viewRef.current.panX = d.startPanX + dx;
        viewRef.current.panY = d.startPanY + dy;
        return;
      }

      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const site = screenToSite(mx, my);
      const { scale } = getTransform();
      const hitRadius = 12 / scale;

      let hit = false;
      for (const a of assetsRef.current) {
        const dx = a.x - site.x;
        const dy = a.y - site.y;
        if (Math.sqrt(dx * dx + dy * dy) < hitRadius) {
          hit = true;
          break;
        }
      }
      canvas.style.cursor = hit ? 'pointer' : 'grab';
    };

    const onMouseUp = (e: MouseEvent) => {
      const wasDrag = dragRef.current.moved;
      dragRef.current.active = false;
      if (!wasDrag) {
        handleCanvasClick(e);
      }
    };

    const onDblClick = () => {
      viewRef.current.zoom = 1;
      viewRef.current.panX = 0;
      viewRef.current.panY = 0;
    };

    canvas.style.cursor = 'grab';
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('dblclick', onDblClick);

    let raf: number;
    const loop = () => {
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const { scale, offset } = getTransform();
      renderFrame(
        ctx,
        zones,
        siteWidth,
        siteHeight,
        assetsRef.current,
        trailsRef.current,
        { showTrails, showHeatmap, showRecs },
        recommendations,
        scale,
        offset,
        selectedAssetId,
      );
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('mousedown', onMouseDown);
      canvas.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('dblclick', onDblClick);
    };
  }, [zones, siteWidth, siteHeight, assetsRef, trailsRef, showTrails, showHeatmap, showRecs, recommendations, getTransform, handleCanvasClick, selectedAssetId]);

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <div className="flex items-center gap-2 px-3 py-2 bg-card border-b border-border">
        <Toggle label="Trails" active={showTrails} onChange={() => setShowTrails(!showTrails)} />
        <Toggle label="Heatmap" active={showHeatmap} onChange={() => setShowHeatmap(!showHeatmap)} />
        <Toggle label="Show Fixes" active={showRecs} onChange={() => setShowRecs(!showRecs)} />
        <div className="w-px h-4 bg-border mx-1" />
        <Toggle label="Cameras" active={showCameras} onChange={() => setShowCameras(!showCameras)} />
      </div>
      <div className={`flex-1 flex ${showCameras ? 'flex-col' : ''} min-h-0`}>
        <div ref={containerRef} className="flex-1 relative">
          <canvas ref={canvasRef} className="absolute inset-0" />
        </div>
        {showCameras && cameraIds.length > 0 && (
          <div className="h-[180px] shrink-0 border-t border-border bg-black flex gap-px">
            {cameraIds.map((id, i) => (
              <CameraFeed key={id} videoId={id} label={`CAM ${i + 1}`} />
            ))}
          </div>
        )}
        {showCameras && cameraIds.length === 0 && (
          <div className="h-[180px] shrink-0 border-t border-border bg-black flex items-center justify-center">
            <span className="text-zinc-500 text-xs">No camera feeds available. Add .mp4 files to backend/vision/videos/</span>
          </div>
        )}
      </div>
    </div>
  );
}
