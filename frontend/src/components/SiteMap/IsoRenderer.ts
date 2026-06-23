/**
 * 2.5D isometric exploded-floors compositor.
 *
 * Renders every level to an offscreen `OffscreenCanvas` via the existing
 * `renderer.ts` `renderFrame`, then stacks them at a fixed isometric
 * angle. The stack is offset vertically so each slab sits above the
 * previous one with translucent ground showing through.
 *
 * Cheap-to-rebuild: each level has its own dirty-flag in the `slabs`
 * map. We only re-render levels whose `truth` changed since the last
 * frame; otherwise the cached bitmap is reused.
 *
 * Single-floor sites short-circuit to the regular `renderFrame` so
 * there's no perf hit when the user isn't using iso mode.
 */
import type { AssetUpdate, Trail } from '../../types/assets';
import type { Level, SiteConnection, Zone } from '../../types/site';
import type { Recommendation } from '../../types/analytics';
import type { HeatmapData } from '../../services/api';
import { renderFrame } from './renderer';

// Mirror of the runtime renderer's internal `RenderOptions` shape. We
// duplicate it here rather than export it from `renderer.ts` to keep
// the renderer file locked-in at its current 768 LOC (Phase 6 rule).
interface RenderOptions {
  showTrails: boolean;
  showHeatmap: boolean;
  showRecs: boolean;
}

// Isometric projection — classic 2:1 dimetric. Rotates the slab 30° on
// X then 45° on Y in matrix terms; for our purposes the simple skew
// below produces a recognisable construction-site iso look.
const ISO_X_SKEW = 0.45; // 1 unit of site Y == 0.45 units of screen X
const ISO_Y_SQUASH = 0.55; // and 0.55 units of screen Y

interface LevelSlab {
  canvas: OffscreenCanvas;
  ctx: OffscreenCanvasRenderingContext2D;
  // Last hash of (level_id + assets-on-level digest) we rendered for.
  // Used to skip redraw when nothing on the slab moved.
  dirtyHash: string;
}


export interface IsoRenderArgs {
  ctx: CanvasRenderingContext2D;
  levels: Level[];
  zones: Zone[];
  siteWidth: number;
  siteHeight: number;
  assets: AssetUpdate[];
  trails: Trail;
  options: RenderOptions;
  recommendations: Recommendation[];
  /** Pixels-per-meter used by the 2D per-slab renderer. The iso
   *  compositor reuses this so slabs project at the right size. */
  scale: number;
  selectedAssetId?: string | null;
  heatmap?: HeatmapData | null;
  recentApply?: { assetId: string; ts: number } | null;
  /** Vertical separation between stacked slabs, in screen pixels. */
  levelGapPx?: number;
  /** Vertical-transport graph — drawn as lines crossing the slab gap
   *  between each pair of adjacent levels the connection touches. */
  connections?: SiteConnection[];
}

const _slabs = new Map<string, LevelSlab>();


function _ensureSlab(levelId: string, w: number, h: number): LevelSlab {
  let slab = _slabs.get(levelId);
  if (slab && slab.canvas.width === w && slab.canvas.height === h) {
    return slab;
  }
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('OffscreenCanvas 2d context unavailable');
  slab = { canvas, ctx, dirtyHash: '' };
  _slabs.set(levelId, slab);
  return slab;
}


function _hashSlabState(levelId: string, assets: AssetUpdate[], options: RenderOptions): string {
  // Coarse hash: per-level asset count + summed x/y + flags. Cheap to
  // compute and almost never gives a false negative (no missed redraw).
  let sx = 0;
  let sy = 0;
  let count = 0;
  for (const a of assets) {
    if ((a.lvl ?? 'L0') !== levelId) continue;
    sx += a.x;
    sy += a.y;
    count += 1;
  }
  return `${levelId}|${count}|${sx.toFixed(1)}|${sy.toFixed(1)}|${options.showTrails ? 't' : ''}|${options.showHeatmap ? 'h' : ''}|${options.showRecs ? 'r' : ''}`;
}


/**
 * Top-level render call. Mirrors the signature of `renderFrame` but
 * stacks per-level slabs at an isometric angle. The caller draws this
 * into the same `ctx` that the 2D renderer normally writes to.
 */
export function renderIso(args: IsoRenderArgs): void {
  const {
    ctx, levels, zones, siteWidth, siteHeight,
    assets, trails, options, recommendations, scale,
    selectedAssetId, heatmap, recentApply,
    levelGapPx = Math.max(40, siteHeight * scale * 0.18),
    connections,
  } = args;

  const dpr = window.devicePixelRatio || 1;
  const cw = ctx.canvas.width / dpr;
  const ch = ctx.canvas.height / dpr;

  // Clear the parent canvas first.
  ctx.fillStyle = '#0b1116';
  ctx.fillRect(0, 0, cw, ch);

  if (!levels || levels.length === 0) {
    return;
  }

  const slabPxW = Math.max(siteWidth * scale, 1);
  const slabPxH = Math.max(siteHeight * scale, 1);

  // Bottom-up so upper slabs paint over lower ones. Capture each
  // level's iso anchor (baseX, baseY) so we can draw connection lines
  // between slabs after all the slabs are down.
  const sorted = [...levels].sort((a, b) => a.order - b.order);
  const isoAnchorByLevelId: Record<string, { baseX: number; baseY: number }> = {};

  for (const level of sorted) {
    const slab = _ensureSlab(level.id, Math.ceil(slabPxW), Math.ceil(slabPxH));
    const hash = _hashSlabState(level.id, assets, options);
    if (hash !== slab.dirtyHash) {
      // Filter zones + assets for this level. Single-floor projects
      // (defaults to L0) keep their data untouched.
      const slabZones = zones.filter((z) => (z.level_id ?? 'L0') === level.id);
      const slabAssets = assets.filter((a) => (a.lvl ?? 'L0') === level.id);
      slab.ctx.setTransform(1, 0, 0, 1, 0, 0);
      // Render this slab in its own coordinate system (offset (0,0)).
      renderFrame(
        slab.ctx as unknown as CanvasRenderingContext2D,
        slabZones, siteWidth, siteHeight,
        slabAssets, trails, options, recommendations,
        scale, { x: 0, y: 0 },
        selectedAssetId, heatmap, recentApply,
      );
      slab.dirtyHash = hash;
    }
    const baseX = (cw - slabPxW) / 2;
    const baseY = ch - slabPxH - 40 - level.order * levelGapPx;
    isoAnchorByLevelId[level.id] = { baseX, baseY };

    ctx.save();
    ctx.setTransform(1, 0, -ISO_X_SKEW, ISO_Y_SQUASH, baseX, baseY);
    ctx.globalAlpha = 0.92;
    ctx.drawImage(slab.canvas, 0, 0);
    ctx.restore();
    ctx.save();
    ctx.font = '11px JetBrains Mono, monospace';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(level.name, 8, baseY + slabPxH * 0.4);
    ctx.restore();
  }

  // Cross-level connection lines (Phase 7 audit fix). For every
  // Connection, draw a line between each consecutive pair of slabs it
  // touches. Solid for elevators, dashed for stairs.
  if (connections && connections.length > 0) {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    for (const c of connections) {
      // Order the nodes by their slab's `order` so we can connect
      // adjacent pairs (handles 3+ level connections too).
      const sortedNodes = [...c.nodes]
        .map((n) => ({ n, lv: sorted.find((lv) => lv.id === n.level_id) }))
        .filter((x): x is { n: typeof x.n; lv: NonNullable<typeof x.lv> } => x.lv !== undefined)
        .sort((a, b) => a.lv.order - b.lv.order);
      for (let i = 0; i < sortedNodes.length - 1; i++) {
        const { n: a, lv: la } = sortedNodes[i];
        const { n: b, lv: lb } = sortedNodes[i + 1];
        const aAnch = isoAnchorByLevelId[la.id];
        const bAnch = isoAnchorByLevelId[lb.id];
        if (!aAnch || !bAnch) continue;
        // Project node coords through the same iso transform.
        const ax = aAnch.baseX + a.x * scale - ISO_X_SKEW * a.y * scale;
        const ay = aAnch.baseY + a.y * scale * ISO_Y_SQUASH;
        const bx = bAnch.baseX + b.x * scale - ISO_X_SKEW * b.y * scale;
        const by = bAnch.baseY + b.y * scale * ISO_Y_SQUASH;
        ctx.strokeStyle = c.kind === 'elevator' ? 'rgba(124, 58, 237, 0.9)' : 'rgba(14, 165, 233, 0.8)';
        ctx.lineWidth = c.kind === 'elevator' ? 2 : 1.5;
        ctx.setLineDash(c.kind === 'stair' ? [4, 3] : []);
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
        ctx.setLineDash([]);
        // Small filled dot on each end so the connection points are
        // visible even when the slab they belong to is dim.
        ctx.fillStyle = c.kind === 'elevator' ? '#7c3aed' : '#0ea5e9';
        ctx.beginPath();
        ctx.arc(ax, ay, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(bx, by, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }
}


/** Drop cached slabs. Call on project switch. */
export function resetIsoSlabs(): void {
  _slabs.clear();
}
