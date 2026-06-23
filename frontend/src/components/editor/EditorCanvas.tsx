/** Editor canvas — minimal 2D drawing focused on the editor's
 * needs: per-level zone outlines, asset markers, click-to-select,
 * drag-to-move (Select tool), and click-to-place (when a placement
 * tool is active).
 *
 * Stays deliberately separate from the runtime `SiteMap` renderer to
 * avoid contaminating the 768-LOC `renderer.ts` with edit-mode logic.
 *
 * Drag-to-move flow:
 *   mousedown over an asset (Select tool) → arm drag
 *   mousemove (while armed)               → repaint with `dragOffset` applied
 *   mouseup                               → if cursor moved >2px,
 *                                            commit ONE `onMoveSelection`
 *                                            patch with the final position.
 *                                            Coarse-grain undo (one history
 *                                            entry per drag).
 *                                            If nearly motionless, treat as
 *                                            a normal click → select only.
 */
import { useEffect, useRef, useState } from 'react';
import { type ProjectDocument } from '../../services/projectsApi';
import { type EditorTool } from './ToolPalette';
import { type EditorSelection } from './PropertiesPanel';
import { API_BASE } from '../../services/api';
import {
  GRID_OPTIONS,
  GRID_STORAGE_KEY,
  loadInitialGrid,
  snapToGrid,
  type GridSize,
} from './grid';

function resolveAssetUrl(url: string): string {
  return url.startsWith('http') ? url : `${API_BASE}${url}`;
}

interface EditorCanvasProps {
  document: ProjectDocument;
  activeLevel: string;
  tool: EditorTool;
  selection: EditorSelection;
  onSelect: (sel: EditorSelection) => void;
  onPlace: (pos: { x: number; y: number }) => void;
  /** Commit the final position of the currently-selected item.
   *  Called once on drag-end so undo is coarse-grain. */
  onMoveSelection: (kind: EditorSelection extends null ? never : NonNullable<EditorSelection>['kind'], id: string, pos: { x: number; y: number }) => void;
}

const FACILITY_COLOR: Record<string, string> = {
  toilet: '#3b82f6',
  breakroom: '#a16207',
  office: '#475569',
  toolcrib: '#6b7280',
};

const EQUIPMENT_COLOR: Record<string, string> = {
  tower_crane: '#dc2626',
  concrete_pump: '#7c3aed',
  excavator: '#ea580c',
  sheet_pile: '#525252',
  // Dewatering pumps are equipment (cycle through OPERATING/IDLE),
  // not facilities — same as the Tiefbau seed.
  dewatering_pump: '#0891b2',
};

// Minimum cursor travel (in pixels) before a click becomes a drag.
const DRAG_THRESHOLD_PX = 3;

type DragKind = NonNullable<EditorSelection>['kind'];

interface DragState {
  kind: DragKind;
  id: string;
  startClientX: number;
  startClientY: number;
  // Site-space position of the asset at drag start. We add dx/dy in
  // site coords (computed each mousemove) and write that to the
  // parent on mouseup.
  assetStartX: number;
  assetStartY: number;
  // Live offset in site coords, updated every mousemove. Used only
  // for the in-canvas preview while dragging.
  dx: number;
  dy: number;
  moved: boolean;
}

export function EditorCanvas({ document, activeLevel, tool, selection, onSelect, onPlace, onMoveSelection }: EditorCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  // Live drag preview state. Mirrors the ref's `{kind, id, dx, dy}` so
  // the paint pass + cursor class can read it during render without
  // tripping the React Compiler's no-refs-in-render rule. Updated by
  // the window mousemove handler, cleared on mouseup.
  const [liveDrag, setLiveDrag] = useState<{ kind: DragKind; id: string; dx: number; dy: number } | null>(null);
  // Hover hit cursor.
  const [hoverHit, setHoverHit] = useState(false);
  // Grid step in meters; 0 means snapping is off. Persisted so the
  // editor remembers the user's preference across reloads.
  const [gridSize, setGridSize] = useState<GridSize>(() => loadInitialGrid());
  // Background floor-plan image cache. Once a URL resolves we never
  // refetch (content-addressed on the backend). Keyed by absolute URL.
  const imgCache = useRef<Map<string, HTMLImageElement | 'pending' | 'failed'>>(new Map());
  // Generic repaint counter — any state change here triggers a
  // re-render and (since the paint effect has no deps) a redraw.
  // Used by ResizeObserver and the async background image loader.
  const [repaintTick, setRepaintTick] = useState(0);
  useEffect(() => {
    try { window.localStorage.setItem(GRID_STORAGE_KEY, String(gridSize)); } catch { /* private mode */ }
  }, [gridSize]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const fit = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = container.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      setRepaintTick((t) => t + 1);
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // Derive screen-space transform. Re-derived every paint so any
  // resize / document edit reflows naturally without re-mounting.
  const getTransform = () => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return { scale: 3, offsetX: 0, offsetY: 0 };
    const rect = container.getBoundingClientRect();
    const pad = 30;
    const scaleX = (rect.width - pad * 2) / document.width;
    const scaleY = (rect.height - pad * 2) / document.height;
    const scale = Math.max(0.5, Math.min(scaleX, scaleY));
    const offsetX = (rect.width - document.width * scale) / 2;
    const offsetY = (rect.height - document.height * scale) / 2;
    return { scale, offsetX, offsetY };
  };

  // Helper: site coords from a screen-space mouse event.
  const screenToSite = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const { scale, offsetX, offsetY } = getTransform();
    return {
      x: (clientX - rect.left - offsetX) / scale,
      y: (clientY - rect.top - offsetY) / scale,
    };
  };

  // Hit-test in priority order: facilities → equipment → materials → connections → zones.
  // Returns the entity + its current site-space (x, y) anchor.
  const hitTest = (sitePos: { x: number; y: number }) => {
    const onActiveLevel = (lv?: string) => (lv ?? 'L0') === activeLevel;
    const hitRadius = 12 / Math.max(getTransform().scale, 0.5);
    for (const f of document.facilities) {
      if (!onActiveLevel(f.level_id)) continue;
      if (Math.hypot(f.x - sitePos.x, f.y - sitePos.y) < hitRadius) {
        return { kind: 'facility' as const, id: f.id, x: f.x, y: f.y };
      }
    }
    for (const e of document.equipment) {
      if (!onActiveLevel(e.level_id)) continue;
      if (Math.hypot(e.x - sitePos.x, e.y - sitePos.y) < hitRadius) {
        return { kind: 'equipment' as const, id: e.id, x: e.x, y: e.y };
      }
    }
    for (const m of document.materials) {
      if (!onActiveLevel(m.level_id)) continue;
      if (Math.hypot(m.x - sitePos.x, m.y - sitePos.y) < hitRadius) {
        return { kind: 'material' as const, id: m.id, x: m.x, y: m.y };
      }
    }
    for (const c of document.connections) {
      const node = c.nodes.find((n) => n.level_id === activeLevel);
      if (!node) continue;
      if (Math.hypot(node.x - sitePos.x, node.y - sitePos.y) < hitRadius) {
        return { kind: 'connection' as const, id: c.id, x: node.x, y: node.y };
      }
    }
    for (const z of document.zones) {
      if (!onActiveLevel(z.level_id)) continue;
      if (sitePos.x >= z.x && sitePos.x <= z.x + z.width && sitePos.y >= z.y && sitePos.y <= z.y + z.height) {
        return { kind: 'zone' as const, id: z.id, x: z.x, y: z.y };
      }
    }
    return null;
  };

  // Drag preview helper: returns the live (x, y) for a given asset,
  // factoring in any in-progress drag. Reads from `liveDrag` state
  // (not the ref) so the paint pass stays render-pure.
  const liveXY = (kind: DragKind, id: string, baseX: number, baseY: number) => {
    if (liveDrag && liveDrag.kind === kind && liveDrag.id === id) {
      return { x: baseX + liveDrag.dx, y: baseY + liveDrag.dy };
    }
    return { x: baseX, y: baseY };
  };

  // Paint pass. Runs on every render (no deps) — cheap, single canvas.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.width / dpr;
    const ch = canvas.height / dpr;

    ctx.fillStyle = '#f0ede8';
    ctx.fillRect(0, 0, cw, ch);

    const { scale, offsetX, offsetY } = getTransform();
    const px = (x: number) => x * scale + offsetX;
    const py = (y: number) => y * scale + offsetY;

    // Background floor-plan image (if the active level has one).
    // Drawn FIRST so it sits beneath the grid + the site outline + every
    // marker. globalAlpha = 0.5 keeps editor markers readable on top.
    const activeLv = document.levels.find((lv) => lv.id === activeLevel);
    const bgUrl = activeLv?.background_image_url ?? null;
    if (bgUrl) {
      const resolved = resolveAssetUrl(bgUrl);
      const cached = imgCache.current.get(resolved);
      if (cached === undefined) {
        // Kick off the load. The image's onload bumps `repaintTick` so
        // the canvas redraws once bytes arrive — without that, no
        // React state would change during the fetch and the empty
        // canvas would stick.
        const img = new window.Image();
        imgCache.current.set(resolved, 'pending');
        img.onload = () => {
          imgCache.current.set(resolved, img);
          setRepaintTick((t) => t + 1);
        };
        img.onerror = () => {
          imgCache.current.set(resolved, 'failed');
          setRepaintTick((t) => t + 1);
        };
        img.src = resolved;
      } else if (cached !== 'pending' && cached !== 'failed') {
        const prevAlpha = ctx.globalAlpha;
        ctx.globalAlpha = 0.5;
        ctx.drawImage(cached, offsetX, offsetY, document.width * scale, document.height * scale);
        ctx.globalAlpha = prevAlpha;
      }
    }

    // Dot grid behind everything. Drawn at the smallest multiple of
    // `gridSize` that produces at least DOT_MIN_PIXELS between dots —
    // for a 300m site on a 310 CSS px canvas (scale ≈ 0.83), drawing
    // every 1m dot would smear into a continuous wash. The visual grid
    // shifts up to 5m / 10m as needed but the SNAP step stays at the
    // user's chosen `gridSize`.
    if (gridSize > 0) {
      const DOT_MIN_PIXELS = 6;
      let visualStep = gridSize;
      while (visualStep * scale < DOT_MIN_PIXELS) visualStep *= 2;
      const prevAlpha = ctx.globalAlpha;
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = '#475569';
      const dotR = 1;
      for (let gx = 0; gx <= document.width + 0.001; gx += visualStep) {
        for (let gy = 0; gy <= document.height + 0.001; gy += visualStep) {
          ctx.beginPath();
          ctx.arc(px(gx), py(gy), dotR, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.globalAlpha = prevAlpha;
    }

    ctx.strokeStyle = '#94a3b8';
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(offsetX, offsetY, document.width * scale, document.height * scale);
    ctx.setLineDash([]);

    for (const z of document.zones) {
      if ((z.level_id ?? 'L0') !== activeLevel) continue;
      const sel = selection?.kind === 'zone' && selection.id === z.id;
      const { x: lx, y: ly } = liveXY('zone', z.id, z.x, z.y);
      ctx.fillStyle = sel ? 'rgba(245, 158, 11, 0.18)' : 'rgba(148, 163, 184, 0.15)';
      ctx.strokeStyle = sel ? '#f59e0b' : '#475569';
      ctx.lineWidth = sel ? 2 : 1;
      ctx.fillRect(px(lx), py(ly), z.width * scale, z.height * scale);
      ctx.strokeRect(px(lx), py(ly), z.width * scale, z.height * scale);
      ctx.fillStyle = '#1f2937';
      ctx.font = '10px Inter, sans-serif';
      ctx.fillText(z.label, px(lx) + 4, py(ly) + 12);
    }

    const drawMarker = (x: number, y: number, color: string, label: string, selected: boolean) => {
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.arc(px(x), py(y), 6, 0, Math.PI * 2);
      ctx.fill();
      if (selected) {
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(px(x), py(y), 9, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = '#1f2937';
      ctx.font = '9px Inter, sans-serif';
      ctx.fillText(label, px(x) + 8, py(y) - 6);
    };

    for (const f of document.facilities) {
      if ((f.level_id ?? 'L0') !== activeLevel) continue;
      const { x, y } = liveXY('facility', f.id, f.x, f.y);
      drawMarker(x, y, FACILITY_COLOR[f.subtype] ?? '#64748b', f.subtype, selection?.kind === 'facility' && selection.id === f.id);
    }
    for (const e of document.equipment) {
      if ((e.level_id ?? 'L0') !== activeLevel) continue;
      const { x, y } = liveXY('equipment', e.id, e.x, e.y);
      drawMarker(x, y, EQUIPMENT_COLOR[e.subtype] ?? '#64748b', e.subtype, selection?.kind === 'equipment' && selection.id === e.id);
    }
    for (const m of document.materials) {
      if ((m.level_id ?? 'L0') !== activeLevel) continue;
      const { x, y } = liveXY('material', m.id, m.x, m.y);
      drawMarker(x, y, '#0891b2', m.subtype, selection?.kind === 'material' && selection.id === m.id);
    }
    for (const c of document.connections) {
      const node = c.nodes.find((n) => n.level_id === activeLevel);
      if (!node) continue;
      const { x, y } = liveXY('connection', c.id, node.x, node.y);
      ctx.beginPath();
      ctx.strokeStyle = c.kind === 'elevator' ? '#7c3aed' : '#0ea5e9';
      ctx.lineWidth = selection?.kind === 'connection' && selection.id === c.id ? 3 : 1.5;
      ctx.arc(px(x), py(y), 8, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#1f2937';
      ctx.font = '9px Inter, sans-serif';
      ctx.fillText(`${c.kind} ${c.id}`, px(x) + 10, py(y) - 6);
    }

    // Help text in the corner.
    ctx.fillStyle = '#64748b';
    ctx.font = '10px Inter, sans-serif';
    const help = tool === 'select'
      ? 'Click to select · drag to move'
      : `Click to place ${tool.replace('add-', '').replace('-', ' ')}`;
    ctx.fillText(help, 8, ch - 8);
  });

  // ── Drag state machine ───────────────────────────────────────────
  //
  // We keep ONE pair of window-level listeners (registered once on mount)
  // that consult `dragRef.current` instead of re-attaching on every
  // mousedown. Re-attaching across React renders would mismatch the
  // listener identity used for `removeEventListener` and leak handlers.

  // Latest callback refs so the stable window listener always uses the
  // current props without remounting.
  const onMoveSelectionRef = useRef(onMoveSelection);
  const documentRef = useRef(document);
  const gridSizeRef = useRef(gridSize);
  useEffect(() => { onMoveSelectionRef.current = onMoveSelection; }, [onMoveSelection]);
  useEffect(() => { documentRef.current = document; }, [document]);
  useEffect(() => { gridSizeRef.current = gridSize; }, [gridSize]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dxPx = e.clientX - d.startClientX;
      const dyPx = e.clientY - d.startClientY;
      if (!d.moved && Math.hypot(dxPx, dyPx) > DRAG_THRESHOLD_PX) {
        d.moved = true;
      }
      if (d.moved) {
        const { scale } = getTransform();
        d.dx = dxPx / scale;
        d.dy = dyPx / scale;
        setLiveDrag({ kind: d.kind, id: d.id, dx: d.dx, dy: d.dy });
      }
    };
    const onUp = () => {
      const d = dragRef.current;
      dragRef.current = null;
      if (d && d.moved) {
        const doc = documentRef.current;
        const grid = gridSizeRef.current;
        const finalX = clamp(snapToGrid(d.assetStartX + d.dx, grid), 0, doc.width);
        const finalY = clamp(snapToGrid(d.assetStartY + d.dy, grid), 0, doc.height);
        onMoveSelectionRef.current(d.kind, d.id, { x: finalX, y: finalY });
      }
      setLiveDrag(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    if (tool !== 'select') return; // placement tools resolve on click
    const sitePos = screenToSite(e.clientX, e.clientY);
    const hit = hitTest(sitePos);
    if (!hit) {
      // Empty click deselects, but no drag is armed.
      onSelect(null);
      return;
    }
    onSelect({ kind: hit.kind, id: hit.id });
    dragRef.current = {
      kind: hit.kind,
      id: hit.id,
      startClientX: e.clientX,
      startClientY: e.clientY,
      assetStartX: hit.x,
      assetStartY: hit.y,
      dx: 0,
      dy: 0,
      moved: false,
    };
  };

  // Click-to-place: only fires when no drag occurred AND a placement tool is active.
  // Empty click in select mode is handled by `onSelect(null)` in handleMouseDown.
  const handleClick = (e: React.MouseEvent) => {
    if (tool === 'select') return; // selection already handled by mousedown
    const sitePos = screenToSite(e.clientX, e.clientY);
    if (sitePos.x < 0 || sitePos.y < 0 || sitePos.x > document.width || sitePos.y > document.height) return;
    onPlace({
      x: snapToGrid(sitePos.x, gridSize),
      y: snapToGrid(sitePos.y, gridSize),
    });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (dragRef.current) return; // cursor is set by drag-active branch below
    if (tool !== 'select') {
      setHoverHit(false);
      return;
    }
    const sitePos = screenToSite(e.clientX, e.clientY);
    setHoverHit(hitTest(sitePos) !== null);
  };

  const cursorClass = tool !== 'select'
    ? 'cursor-crosshair'
    : liveDrag
      ? 'cursor-grabbing'
      : hoverHit
        ? 'cursor-grab'
        : 'cursor-default';

  // Mark the state values consumed by the paint effect — without these,
  // React Compiler's purity rules complain that the effect reads state
  // outside its dep array. The paint effect runs on every render so
  // these reads happen as a side-effect of re-rendering.
  void liveDrag;
  void repaintTick;

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <GridToolbar value={gridSize} onChange={setGridSize} />
      <div ref={containerRef} className="flex-1 relative bg-secondary/40">
        <canvas
          ref={canvasRef}
          className={`absolute inset-0 ${cursorClass}`}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onClick={handleClick}
        />
      </div>
    </div>
  );
}

function GridToolbar({ value, onChange }: { value: GridSize; onChange: (g: GridSize) => void }) {
  return (
    <div
      data-testid="grid-toolbar"
      className="flex items-center gap-1 px-2 py-1 border-b border-border bg-card text-[10px]"
    >
      <span className="uppercase tracking-wider text-muted-foreground mr-1">Snap</span>
      {GRID_OPTIONS.map((g) => (
        <button
          key={g}
          type="button"
          onClick={() => onChange(g)}
          aria-pressed={g === value}
          className={
            'px-2 py-0.5 rounded-full border ' +
            (g === value
              ? 'border-primary bg-primary/10 text-foreground'
              : 'border-border hover:bg-secondary text-muted-foreground')
          }
        >
          {g === 0 ? 'Off' : `${g}m`}
        </button>
      ))}
    </div>
  );
}


function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}
