import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import type { AssetUpdate, Trail } from '../../types/assets';
import type { Level, Road, SiteConnection, Zone } from '../../types/site';
import type { Recommendation } from '../../types/analytics';
import type { CabSnapshot } from '../../hooks/useWebSocket';
import { Toggle } from '../common/Toggle';
import { renderFrame } from './renderer';
import { renderIso, resetIsoSlabs } from './IsoRenderer';
import { CameraFeed } from './CameraFeed';
import { LevelSwitcher } from './LevelSwitcher';
import { API_BASE, fetchCameras, fetchHeatmap, type HeatmapData } from '../../services/api';

const DEFAULT_LEVEL_ID = 'L0';

interface SiteMapProps {
  zones: Zone[];
  siteWidth: number;
  siteHeight: number;
  assetsRef: React.MutableRefObject<AssetUpdate[]>;
  trailsRef: React.MutableRefObject<Trail>;
  /** Live cab snapshots from the WS payload. Drives the per-anchor
   *  queue / passenger overlay drawn on top of the runtime renderer. */
  cabsRef?: React.MutableRefObject<CabSnapshot[]>;
  recommendations: Recommendation[];
  selectedAssetId: string | null;
  onAssetSelect: (id: string | null) => void;
  /** Last asset modified by an Apply action — drives the pulsing
   *  "recently changed" ring on the map. */
  recentApply?: { assetId: string; ts: number } | null;
  /** Multi-level (Phase 6). When provided + length > 1, the LevelSwitcher
   *  shows and zones/assets are filtered by the active level. */
  levels?: Level[];
  /** Vertical-transport graph. Used to look up anchor positions on the
   *  active level when drawing the cab queue overlay. */
  connections?: SiteConnection[];
  /** Authored walkable corridors. When provided, the renderer draws
   *  these instead of the legacy hardcoded south + west perimeter. */
  roads?: Road[];
}

export function SiteMap({ zones, siteWidth, siteHeight, assetsRef, trailsRef, cabsRef, recommendations, selectedAssetId, onAssetSelect, recentApply, levels, connections, roads }: SiteMapProps) {
  const [activeLevel, setActiveLevel] = useState<string>(DEFAULT_LEVEL_ID);

  // Reset activeLevel + iso-slab cache whenever the project changes
  // (the levels list is the canonical signal of a project switch).
  useEffect(() => {
    resetIsoSlabs();
    if (!levels || levels.length === 0) {
      setActiveLevel(DEFAULT_LEVEL_ID);
      return;
    }
    if (!levels.some((lv) => lv.id === activeLevel)) {
      const fallback = levels.find((lv) => lv.id === DEFAULT_LEVEL_ID) ?? [...levels].sort((a, b) => a.order - b.order)[0];
      setActiveLevel(fallback.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [levels]);

  // Filter zones by the active level. Single-level projects pass through.
  const visibleZones = useMemo(() => {
    if (!levels || levels.length <= 1) return zones;
    return zones.filter((z) => (z.level_id ?? DEFAULT_LEVEL_ID) === activeLevel);
  }, [zones, levels, activeLevel]);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef({ w: 0, h: 0 });
  const [showTrails, setShowTrails] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showRecs, setShowRecs] = useState(true);
  const [showCameras, setShowCameras] = useState(false);
  const [cameraIds, setCameraIds] = useState<string[]>([]);
  // Phase 7: iso exploded-floors view. Only meaningful for multi-level
  // projects; the toggle hides itself otherwise.
  const [isoView, setIsoView] = useState(false);
  // Heatmap data lives in a ref so we don't re-render the SiteMap effect
  // on every poll tick (would tear down the RAF loop).
  const heatmapRef = useRef<HeatmapData | null>(null);

  useEffect(() => {
    if (showCameras && cameraIds.length === 0) {
      fetchCameras()
        .then((cams) => setCameraIds(cams.map(c => c.id)))
        .catch(() => {});
    }
  }, [showCameras, cameraIds.length]);

  // Poll the heatmap endpoint while the toggle is on. Stop polling +
  // discard the grid when toggled off so the renderer falls back to the
  // empty-state and zone phases are clearly readable.
  //
  // Multi-level: the poll passes the active level so the grid we draw
  // matches the slab the user is looking at. Single-floor projects
  // pass undefined → pooled view (same as legacy behaviour).
  useEffect(() => {
    if (!showHeatmap) {
      heatmapRef.current = null;
      return;
    }
    const isMultiLevel = (levels?.length ?? 0) > 1;
    let cancelled = false;
    const load = () => {
      fetchHeatmap(isMultiLevel ? activeLevel : undefined)
        .then((data) => { if (!cancelled) heatmapRef.current = data; })
        .catch(() => {});
    };
    load();
    const interval = window.setInterval(load, 1500);
    return () => { cancelled = true; clearInterval(interval); };
  }, [showHeatmap, activeLevel, levels]);

  // Floor-plan background image cache. Keyed by absolute URL; entries
  // are 'pending' while a fetch is in flight, the <img> once loaded,
  // 'failed' if the load errored. Mirrors EditorCanvas's pattern so
  // the runtime + edit modes behave identically. Kept here (rather
  // than threaded through renderer.ts) so the 768-LOC renderer stays
  // unchanged — same rule as the iso-slab + cab overlay handling.
  const bgImageCache = useRef<Map<string, HTMLImageElement | 'pending' | 'failed'>>(new Map());

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
      // Restore cursor immediately rather than waiting for the next
      // mousemove to recompute hover state.
      canvas.style.cursor = 'grab';
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
    // Window-level mousemove handles both hover hit-testing AND drag-with-
    // cursor-outside-canvas. Registering it on the canvas as well would
    // double the per-frame hit test cost (the loop iterates all assets).
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('dblclick', onDblClick);

    let raf: number;
    // Per-asset interpolated "display position". Lazily seeded the first
    // time we see each asset, then lerped toward the true position each
    // frame. Big jumps (apply-rec moves) become smooth glides; per-tick
    // FSM movement stays imperceptibly close to the real value.
    const displayPos = new Map<string, { x: number; y: number }>();
    // Quick-lookup: if a position delta is larger than this, treat as a
    // teleport that should animate slowly. Otherwise we use a fast lerp.
    const TELEPORT_THRESHOLD_M = 8;
    const FAST_LERP = 0.5; // ~6m worker steps catch up in 1 frame
    const SLOW_LERP = 0.12; // ~700ms ease toward target for big moves

    const isMultiLevel = (levels?.length ?? 0) > 1;
    const loop = () => {
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const { scale, offset } = getTransform();

      // Build a display-asset list: same shape as assets, but with
      // smoothed x/y. Reuse the AssetUpdate object identity so any
      // downstream code that compares by ref doesn't notice.
      const truth = assetsRef.current;
      const displayAssets: AssetUpdate[] = [];
      const seen = new Set<string>();
      for (const a of truth) {
        seen.add(a.id);
        // Multi-level filter: skip assets on a level the user isn't
        // looking at. Single-floor projects (isMultiLevel === false)
        // skip the filter entirely and behave exactly as before.
        if (isMultiLevel && (a.lvl ?? DEFAULT_LEVEL_ID) !== activeLevel) {
          continue;
        }
        const prev = displayPos.get(a.id);
        if (!prev) {
          displayPos.set(a.id, { x: a.x, y: a.y });
          displayAssets.push(a);
          continue;
        }
        const dx = a.x - prev.x;
        const dy = a.y - prev.y;
        const dist = Math.hypot(dx, dy);
        if (dist < 0.05) {
          // Snap & avoid drift
          prev.x = a.x;
          prev.y = a.y;
          displayAssets.push(a);
          continue;
        }
        const lerp = dist > TELEPORT_THRESHOLD_M ? SLOW_LERP : FAST_LERP;
        prev.x += dx * lerp;
        prev.y += dy * lerp;
        // Clone the asset object with smoothed coords (cheap — small object)
        displayAssets.push({ ...a, x: prev.x, y: prev.y });
      }
      // Drop stale entries (assets removed by load_project)
      for (const id of displayPos.keys()) if (!seen.has(id)) displayPos.delete(id);

      if (isoView && isMultiLevel) {
        // Iso compositor reuses the truth list (every level) since it
        // builds one slab per level. The display-asset smoothing above
        // already applied a level filter for the 2D view, so for the
        // iso path we pass the raw `truth` after the same smoothing
        // (but without the level filter).
        const isoAssets: AssetUpdate[] = [];
        for (const a of truth) {
          const prev = displayPos.get(a.id);
          isoAssets.push(prev ? { ...a, x: prev.x, y: prev.y } : a);
        }
        renderIso({
          ctx, levels: levels ?? [], zones,
          siteWidth, siteHeight,
          assets: isoAssets, trails: trailsRef.current,
          options: { showTrails, showHeatmap, showRecs },
          recommendations, scale,
          selectedAssetId, heatmap: heatmapRef.current, recentApply,
          connections, roads,
        });
      } else {
        // Background floor-plan image for the active level, if any.
        // Renderer.ts is locked-in (Phase-6 rule) and begins its draw
        // with an opaque beige fillRect that would wipe any paint we
        // do beforehand. So we (1) draw the background, then (2)
        // temporarily intercept the very first beige fillRect call so
        // renderer keeps the rest of its drawing pipeline intact while
        // our background survives underneath the zones / workers /
        // trails. Restored before the function returns.
        const activeLv = levels?.find((lv) => lv.id === activeLevel);
        const bgUrl = activeLv?.background_image_url ?? null;
        let bgImage: HTMLImageElement | null = null;
        if (bgUrl) {
          const resolved = bgUrl.startsWith('http') ? bgUrl : `${API_BASE}${bgUrl}`;
          const cached = bgImageCache.current.get(resolved);
          if (cached === undefined) {
            const img = new window.Image();
            bgImageCache.current.set(resolved, 'pending');
            img.onload = () => { bgImageCache.current.set(resolved, img); };
            img.onerror = () => { bgImageCache.current.set(resolved, 'failed'); };
            img.src = resolved;
          } else if (cached !== 'pending' && cached !== 'failed') {
            bgImage = cached;
          }
        }

        const origFillRect = ctx.fillRect.bind(ctx) as typeof ctx.fillRect;
        if (bgImage) {
          // Paint the background up front (opaque, full alpha). We then
          // intercept renderer.ts's first two opaque solid-colour fills
          // — the full-canvas beige clear (#f0ede8) and the site-area
          // sandy ground (#d4c9a8) — so the user's floor-plan survives.
          // Every other fillRect (zone shadows, scale bar, road
          // markings, etc.) goes through unchanged. Once the renderer
          // is past those two fills the rest of its pipeline draws on
          // top of the background image, giving us the "background
          // behind everything" composition the editor canvas uses.
          ctx.drawImage(bgImage, offset.x, offset.y, siteWidth * scale, siteHeight * scale);
          let suppressed = 0;
          ctx.fillRect = ((x: number, y: number, w: number, h: number): void => {
            if (suppressed < 2) {
              const style = ctx.fillStyle;
              if (style === '#f0ede8' || style === '#d4c9a8') {
                suppressed += 1;
                return;
              }
            }
            origFillRect(x, y, w, h);
          }) as typeof ctx.fillRect;
        }

        renderFrame(
          ctx,
          visibleZones,
          siteWidth,
          siteHeight,
          displayAssets,
          trailsRef.current,
          { showTrails, showHeatmap, showRecs },
          recommendations,
          scale,
          offset,
          selectedAssetId,
          heatmapRef.current,
          recentApply,
          (roads ?? []).filter((r) => (r.level_id ?? DEFAULT_LEVEL_ID) === activeLevel),
        );
        if (bgImage) {
          // Restore the original fillRect so the rest of the frame
          // (cab overlay) sees the un-patched API.
          ctx.fillRect = origFillRect;
        }
        // Multi-level overlay: draw queue / cross-level indicators on
        // top of the runtime renderer without touching `renderer.ts`.
        // `connections` carries the static anchor positions; `cabsRef`
        // carries the live queue depths streamed via WS.
        if (isMultiLevel && connections && connections.length > 0 && cabsRef) {
          drawCabOverlay(
            ctx,
            connections,
            cabsRef.current,
            activeLevel,
            scale,
            offset,
          );
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('dblclick', onDblClick);
    };
  }, [zones, siteWidth, siteHeight, assetsRef, trailsRef, cabsRef, showTrails, showHeatmap, showRecs, recommendations, getTransform, handleCanvasClick, selectedAssetId, recentApply, activeLevel, levels, visibleZones, isoView, connections, roads]);

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <div className="flex items-center gap-2 px-3 py-2 bg-card border-b border-border">
        <Toggle label="Trails" active={showTrails} onChange={() => setShowTrails(!showTrails)} />
        <Toggle label="Heatmap" active={showHeatmap} onChange={() => setShowHeatmap(!showHeatmap)} />
        <Toggle label="Show Fixes" active={showRecs} onChange={() => setShowRecs(!showRecs)} />
        <div className="w-px h-4 bg-border mx-1" />
        {levels && levels.length > 1 && (
          <Toggle label="Iso View" active={isoView} onChange={() => setIsoView(!isoView)} />
        )}
        <Toggle label="Cameras" active={showCameras} onChange={() => setShowCameras(!showCameras)} />
      </div>
      <div className={`flex-1 flex ${showCameras ? 'flex-col' : ''} min-h-0`}>
        <div ref={containerRef} className="flex-1 relative">
          <canvas ref={canvasRef} className="absolute inset-0" />
          {levels && levels.length > 1 && (
            <LevelSwitcher levels={levels} activeLevel={activeLevel} onLevelChange={setActiveLevel} />
          )}
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


/**
 * Overlay cross-level activity counters on each connection's anchor
 * on the currently-visible level:
 *   - Total waiting workers on THIS level
 *   - Up/down arrow showing where the cab is going
 *   - Total waiting workers on OTHER levels combined (smaller, dim)
 *
 * Kept outside `renderer.ts` so the runtime renderer stays unchanged.
 * Runs after `renderFrame` so the overlay paints on top of the marker.
 */
function drawCabOverlay(
  ctx: CanvasRenderingContext2D,
  connections: SiteConnection[],
  cabs: CabSnapshot[],
  activeLevel: string,
  scale: number,
  offset: { x: number; y: number },
): void {
  const cabById: Record<string, CabSnapshot> = {};
  for (const c of cabs) cabById[c.id] = c;
  const px = (x: number) => x * scale + offset.x;
  const py = (y: number) => y * scale + offset.y;

  for (const conn of connections) {
    const node = conn.nodes.find((n) => n.level_id === activeLevel);
    if (!node) continue;
    const cab = cabById[conn.id];
    if (!cab && conn.kind !== 'stair') {
      // Stairs have no cab; the static anchor is enough — skip overlay.
      continue;
    }
    const hereQueue = cab?.queue_by_level[activeLevel] ?? 0;
    let elsewhereQueue = 0;
    if (cab) {
      for (const [lv, n] of Object.entries(cab.queue_by_level)) {
        if (lv !== activeLevel) elsewhereQueue += n;
      }
    }
    if (hereQueue === 0 && elsewhereQueue === 0 && (cab?.passengers ?? 0) === 0) {
      continue;
    }
    const ax = px(node.x);
    const ay = py(node.y);

    // Background pill behind the count(s).
    const pillW = elsewhereQueue > 0 ? 56 : 36;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
    ctx.beginPath();
    if (typeof ctx.roundRect === 'function') {
      ctx.roundRect(ax + 10, ay - 22, pillW, 16, 8);
    } else {
      ctx.rect(ax + 10, ay - 22, pillW, 16);
    }
    ctx.fill();

    ctx.fillStyle = '#f8fafc';
    ctx.font = '10px JetBrains Mono, monospace';
    const hereLabel = `${hereQueue > 0 ? '↑' : '·'} ${hereQueue}`;
    ctx.fillText(hereLabel, ax + 16, ay - 11);
    if (elsewhereQueue > 0) {
      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`+${elsewhereQueue}↕`, ax + 38, ay - 11);
    }
    // Direction tick: small arrow above the anchor pointing to the
    // floor where the cab currently is (rough cue of where it's heading).
    if (cab) {
      const goingUp = cab.current_level !== activeLevel;
      ctx.fillStyle = goingUp ? '#fbbf24' : '#22c55e';
      ctx.font = '10px Inter, sans-serif';
      ctx.fillText(goingUp ? '↑' : '✓', ax - 2, ay - 11);
    }
  }
}
