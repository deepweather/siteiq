import type { AssetUpdate, Trail } from '../../types/assets';
import type { Zone } from '../../types/site';
import type { Recommendation } from '../../types/analytics';
import { TRADE_COLORS } from '../../utils/colors';

interface RenderOptions {
  showTrails: boolean;
  showHeatmap: boolean;
  showRecs: boolean;
}

let S = 1;
let OX = 0;
let OY = 0;
function px(x: number) { return x * S + OX; }
function py(y: number) { return y * S + OY; }
function ps(v: number) { return v * S; }

export function renderFrame(
  ctx: CanvasRenderingContext2D,
  zones: Zone[],
  siteWidth: number,
  siteHeight: number,
  assets: AssetUpdate[],
  trails: Trail,
  options: RenderOptions,
  recommendations: Recommendation[],
  scale: number,
  offset: { x: number; y: number },
  selectedAssetId?: string | null,
) {
  const dpr = window.devicePixelRatio || 1;
  const cw = ctx.canvas.width / dpr;
  const ch = ctx.canvas.height / dpr;
  S = scale;
  OX = offset.x;
  OY = offset.y;

  ctx.fillStyle = '#f0ede8';
  ctx.fillRect(0, 0, cw, ch);

  drawSiteGround(ctx, siteWidth, siteHeight);
  drawAccessRoads(ctx, siteWidth, siteHeight);
  drawSiteFence(ctx, siteWidth, siteHeight);

  drawZoneStructures(ctx, zones);

  const materials = assets.filter(a => a.type === 'material');
  const facilities = assets.filter(a => a.type === 'facility');
  const equipment = assets.filter(a => a.type === 'equipment');
  const workers = assets.filter(a => a.type === 'worker');

  if (options.showHeatmap) drawHeatmap(ctx, trails, siteWidth, siteHeight);
  if (options.showTrails) drawTrails(ctx, trails, workers, selectedAssetId);

  drawMaterialStacks(ctx, materials);
  drawFacilityStructures(ctx, facilities);
  drawEquipmentTopDown(ctx, equipment);
  drawWorkerFigures(ctx, workers);

  if (options.showRecs) drawRecommendationArrows(ctx, recommendations);

  if (selectedAssetId) drawSelectionHighlight(ctx, assets, selectedAssetId);

  drawScaleBar(ctx, cw, ch);
  drawLegend(ctx, cw);
}

function drawSiteGround(ctx: CanvasRenderingContext2D, sw: number, sh: number) {
  ctx.fillStyle = '#d4c9a8';
  ctx.fillRect(px(0), py(0), ps(sw), ps(sh));

  ctx.fillStyle = 'rgba(0,0,0,0.03)';
  const seed = 42;
  for (let i = 0; i < 400; i++) {
    const rx = ((seed * (i * 7 + 3)) % 1000) / 1000 * sw;
    const ry = ((seed * (i * 13 + 7)) % 1000) / 1000 * sh;
    ctx.fillRect(px(rx), py(ry), ps(1.5), ps(1));
  }
}

function drawAccessRoads(ctx: CanvasRenderingContext2D, sw: number, sh: number) {
  ctx.fillStyle = '#a8a090';
  ctx.fillRect(px(0), py(sh - 12), ps(sw), ps(12));

  ctx.strokeStyle = 'rgba(255,255,255,0.4)';
  ctx.lineWidth = 1;
  ctx.setLineDash([ps(4), ps(3)]);
  ctx.beginPath();
  ctx.moveTo(px(0), py(sh - 6));
  ctx.lineTo(px(sw), py(sh - 6));
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = '#a8a090';
  ctx.fillRect(px(0), py(0), ps(8), ps(sh));

  ctx.fillStyle = '#8a8070';
  ctx.fillRect(px(sw / 2 - 10), py(sh - 14), ps(20), ps(14));
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.font = `${Math.max(7, ps(3))}px Inter, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('GATE', px(sw / 2), py(sh - 7));
}

function drawSiteFence(ctx: CanvasRenderingContext2D, sw: number, sh: number) {
  ctx.strokeStyle = 'rgba(120,100,50,0.4)';
  ctx.lineWidth = 2;
  ctx.setLineDash([ps(2), ps(1.5)]);
  ctx.strokeRect(px(-1), py(-1), ps(sw + 2), ps(sh + 2));
  ctx.setLineDash([]);

  ctx.fillStyle = 'rgba(120,100,50,0.5)';
  for (let x = 0; x <= sw; x += 20) {
    ctx.fillRect(px(x) - 1.5, py(-1) - 1, 3, 3);
    ctx.fillRect(px(x) - 1.5, py(sh) - 1, 3, 3);
  }
  for (let y = 0; y <= sh; y += 20) {
    ctx.fillRect(px(-1) - 1, py(y) - 1.5, 3, 3);
    ctx.fillRect(px(sw) - 1, py(y) - 1.5, 3, 3);
  }
}

function drawZoneStructures(ctx: CanvasRenderingContext2D, zones: Zone[]) {
  for (const z of zones) {
    const x = px(z.x);
    const y = py(z.y);
    const w = ps(z.width);
    const h = ps(z.height);

    if (z.phase === 'excavation') {
      drawExcavation(ctx, x, y, w, h);
    } else if (z.phase === 'foundation') {
      drawFoundation(ctx, x, y, w, h);
    } else if (z.phase === 'structural') {
      drawStructural(ctx, x, y, w, h);
    } else if (z.phase === 'mep_roughin') {
      drawMEP(ctx, x, y, w, h);
    } else if (z.phase === 'finishes') {
      drawFinishes(ctx, x, y, w, h);
    } else {
      ctx.fillStyle = '#e8e4dc';
      ctx.fillRect(x, y, w, h);
    }

    const label = z.label;
    const fontSize = Math.max(8, Math.min(11, w / 8));
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    const tw = ctx.measureText(label).width + 12;
    roundRect(ctx, x + 3, y + 3, Math.max(tw, ps(12)), fontSize + 6, 2);
    ctx.fill();
    ctx.fillStyle = '#333';
    ctx.font = `700 ${fontSize}px Inter, sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(label, x + 7, y + 6);
  }
}

function drawExcavation(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = '#b8a070';
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = 'rgba(100,70,30,0.3)';
  ctx.lineWidth = 1;
  const step = Math.max(8, h / 6);
  for (let i = 1; i < 5; i++) {
    const inset = i * step * 0.15;
    ctx.strokeRect(x + inset, y + inset, w - inset * 2, h - inset * 2);
  }

  ctx.fillStyle = 'rgba(100,70,30,0.15)';
  ctx.beginPath();
  ctx.ellipse(x + w * 0.8, y + h * 0.2, w * 0.15, h * 0.12, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = 'rgba(100,70,30,0.15)';
  ctx.lineWidth = 0.5;
  for (let i = 0; i < w; i += 6) {
    ctx.beginPath();
    ctx.moveTo(x + i, y);
    ctx.lineTo(x + i + 3, y + 4);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x + i, y + h);
    ctx.lineTo(x + i + 3, y + h - 4);
    ctx.stroke();
  }
}

function drawFoundation(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = '#c0b898';
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = 'rgba(80,70,50,0.3)';
  ctx.lineWidth = ps(0.8);
  const cols = 4;
  const rows = 3;
  const cellW = w / cols;
  const cellH = h / rows;

  for (let c = 0; c <= cols; c++) {
    ctx.beginPath();
    ctx.moveTo(x + c * cellW, y);
    ctx.lineTo(x + c * cellW, y + h);
    ctx.stroke();
  }
  for (let r = 0; r <= rows; r++) {
    ctx.beginPath();
    ctx.moveTo(x, y + r * cellH);
    ctx.lineTo(x + w, y + r * cellH);
    ctx.stroke();
  }

  ctx.fillStyle = 'rgba(80,70,50,0.12)';
  for (let c = 0; c <= cols; c++) {
    for (let r = 0; r <= rows; r++) {
      const fx = x + c * cellW;
      const fy = y + r * cellH;
      ctx.fillRect(fx - ps(2), fy - ps(2), ps(4), ps(4));
    }
  }
}

function drawStructural(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = '#ccc8c0';
  ctx.fillRect(x, y, w, h);

  const cols = 5;
  const rows = 4;
  const cellW = w / cols;
  const cellH = h / rows;

  ctx.strokeStyle = 'rgba(60,60,60,0.2)';
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);

  ctx.fillStyle = 'rgba(60,60,60,0.25)';
  for (let c = 1; c < cols; c++) {
    for (let r = 1; r < rows; r++) {
      const cx = x + c * cellW;
      const cy = y + r * cellH;
      ctx.fillRect(cx - ps(1), cy - ps(1), ps(2), ps(2));
    }
  }

  ctx.strokeStyle = 'rgba(60,60,60,0.1)';
  ctx.lineWidth = ps(0.4);
  for (let c = 1; c < cols; c++) {
    ctx.beginPath();
    ctx.moveTo(x + c * cellW, y + cellH);
    ctx.lineTo(x + c * cellW, y + h - cellH);
    ctx.stroke();
  }
  for (let r = 1; r < rows; r++) {
    ctx.beginPath();
    ctx.moveTo(x + cellW, y + r * cellH);
    ctx.lineTo(x + w - cellW, y + r * cellH);
    ctx.stroke();
  }

  ctx.strokeStyle = 'rgba(180,80,50,0.2)';
  ctx.lineWidth = 1;
  for (let c = 1; c < cols; c += 2) {
    for (let r = 1; r < rows; r += 2) {
      const cx = x + c * cellW + cellW / 2;
      const cy = y + r * cellH + cellH / 2;
      const s = ps(1.5);
      ctx.beginPath();
      ctx.moveTo(cx - s, cy - s); ctx.lineTo(cx + s, cy + s);
      ctx.moveTo(cx + s, cy - s); ctx.lineTo(cx - s, cy + s);
      ctx.stroke();
    }
  }
}

function drawMEP(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = '#d8d0e0';
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = 'rgba(60,60,80,0.25)';
  ctx.lineWidth = ps(0.6);
  ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);

  ctx.strokeStyle = 'rgba(60,60,80,0.15)';
  ctx.lineWidth = ps(0.5);
  ctx.beginPath();
  ctx.moveTo(x, y + h * 0.4);
  ctx.lineTo(x + w * 0.7, y + h * 0.4);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + w * 0.3, y + h * 0.7);
  ctx.lineTo(x + w, y + h * 0.7);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + w * 0.5, y);
  ctx.lineTo(x + w * 0.5, y + h * 0.4);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(70,70,200,0.25)';
  ctx.lineWidth = ps(0.4);
  ctx.setLineDash([ps(1), ps(1)]);
  ctx.beginPath();
  ctx.moveTo(x + 4, y + h * 0.2);
  ctx.lineTo(x + w - 4, y + h * 0.2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + w * 0.3, y + 4);
  ctx.lineTo(x + w * 0.3, y + h - 4);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.strokeStyle = 'rgba(220,140,30,0.2)';
  ctx.lineWidth = ps(0.3);
  ctx.setLineDash([ps(0.5), ps(1.5)]);
  ctx.beginPath();
  ctx.moveTo(x + w * 0.6, y + 4);
  ctx.lineTo(x + w * 0.6, y + h * 0.5);
  ctx.lineTo(x + w - 4, y + h * 0.5);
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawFinishes(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = '#e0ddd5';
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = 'rgba(60,60,60,0.3)';
  ctx.lineWidth = ps(0.8);
  ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);

  ctx.strokeStyle = 'rgba(60,60,60,0.2)';
  ctx.lineWidth = ps(0.6);
  ctx.beginPath();
  ctx.moveTo(x + w * 0.35, y + 2);
  ctx.lineTo(x + w * 0.35, y + h - 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + w * 0.65, y + 2);
  ctx.lineTo(x + w * 0.65, y + h * 0.5);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + 2, y + h * 0.5);
  ctx.lineTo(x + w - 2, y + h * 0.5);
  ctx.stroke();

  ctx.fillStyle = '#e0ddd5';
  ctx.fillRect(x + ps(w / S * 0.35) - 1, y + h * 0.22, 3, ps(4));
  ctx.fillRect(x + w * 0.5, y + h * 0.5 - 1, ps(4), 3);

  ctx.strokeStyle = 'rgba(60,60,60,0.06)';
  ctx.lineWidth = 0.5;
  const tileSize = ps(3);
  for (let tx = x + 2; tx < x + w * 0.35; tx += tileSize) {
    for (let ty = y + 2; ty < y + h * 0.5; ty += tileSize) {
      ctx.strokeRect(tx, ty, tileSize, tileSize);
    }
  }
}

function drawWorkerFigures(ctx: CanvasRenderingContext2D, workers: AssetUpdate[]) {
  const iconSize = Math.max(10, ps(5));

  for (const w of workers) {
    const x = px(w.x);
    const y = py(w.y);
    const color = TRADE_COLORS[w.subtype] || '#94a3b8';
    const isWalking = w.state.startsWith('walking_') || w.state === 'carrying_material';
    const isAtFacility = w.state === 'at_toilet' || w.state === 'at_break';

    if (isAtFacility) ctx.globalAlpha = 0.3;

    ctx.beginPath();
    ctx.arc(x, y + 1, Math.max(3, iconSize * 0.35), 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();

    ctx.font = `${iconSize}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(isAtFacility ? '🧍' : '👷', x, y - 1);

    if (isWalking) {
      ctx.beginPath();
      ctx.arc(x, y, iconSize * 0.6, 0, Math.PI * 2);
      const [r, g, b] = hexToRgb(color);
      ctx.fillStyle = `rgba(${r},${g},${b},0.15)`;
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  }
}

function drawTrails(ctx: CanvasRenderingContext2D, trails: Trail, workers: AssetUpdate[], selectedAssetId?: string | null) {
  const workerMap = new Map(workers.map(w => [w.id, w]));
  const hasSelection = !!selectedAssetId;

  for (const [id, positions] of Object.entries(trails)) {
    if (positions.length < 3) continue;
    const isSelected = id === selectedAssetId;
    const worker = workerMap.get(id);
    const hex = worker ? (TRADE_COLORS[worker.subtype] || '#94a3b8') : '#94a3b8';
    const [r, g, b] = hexToRgb(hex);
    const len = positions.length;

    const maxAlpha = hasSelection ? (isSelected ? 0.7 : 0.04) : 0.35;
    ctx.lineWidth = isSelected ? 1.5 : 0.8;

    for (let i = 1; i < len; i++) {
      const alpha = (i / len) * maxAlpha;
      ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.beginPath();
      ctx.moveTo(px(positions[i - 1][0]), py(positions[i - 1][1]));
      ctx.lineTo(px(positions[i][0]), py(positions[i][1]));
      ctx.stroke();
    }
  }
}

function drawEquipmentTopDown(ctx: CanvasRenderingContext2D, equipment: AssetUpdate[]) {
  const iconSize = Math.max(20, ps(12));
  const labelFont = `700 ${Math.max(7, ps(2.5))}px 'JetBrains Mono', monospace`;

  const ICONS: Record<string, string> = {
    tower_crane: '🏗️',
    concrete_pump: '🚛',
    excavator: '🚜',
  };
  const LABELS: Record<string, string> = {
    tower_crane: 'CRANE',
    concrete_pump: 'PUMP',
    excavator: 'EXCAVATOR',
  };

  for (const e of equipment) {
    if (e.state === 'removed') continue;
    const x = px(e.x);
    const y = py(e.y);
    const operating = e.state === 'operating';

    const glowR = iconSize * 0.75;

    // Outer status ring
    ctx.beginPath();
    ctx.arc(x, y, glowR, 0, Math.PI * 2);
    ctx.fillStyle = operating ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)';
    ctx.fill();
    ctx.strokeStyle = operating ? '#16a34a' : '#dc2626';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Solid background behind icon so it's not occluded by zone textures
    ctx.beginPath();
    ctx.arc(x, y, iconSize * 0.5, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fill();

    // Icon
    ctx.font = `${iconSize}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ICONS[e.subtype] || '⚙️', x, y);

    ctx.font = labelFont;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillText(LABELS[e.subtype] || e.subtype, x, y + glowR + 2);
    ctx.fillStyle = operating ? '#16a34a' : '#dc2626';
    ctx.fillText(operating ? 'ACTIVE' : 'IDLE', x, y + glowR + 2 + Math.max(9, ps(3)));
  }
}

function drawFacilityStructures(ctx: CanvasRenderingContext2D, facilities: AssetUpdate[]) {
  const iconSize = Math.max(18, ps(10));
  const labelFont = `700 ${Math.max(7, ps(2.5))}px 'JetBrains Mono', monospace`;

  const ICONS: Record<string, string> = {
    toilet: '🚻',
    breakroom: '☕',
    office: '🏢',
    toolcrib: '🔧',
  };
  const LABELS: Record<string, string> = {
    toilet: 'WC',
    breakroom: 'BREAK',
    office: 'OFFICE',
    toolcrib: 'TOOLS',
  };
  const BORDER_COLORS: Record<string, string> = {
    toilet: '#2563eb',
    breakroom: '#16a34a',
    office: '#ca8a04',
    toolcrib: '#ea580c',
  };

  for (const f of facilities) {
    const x = px(f.x);
    const y = py(f.y);
    const borderColor = BORDER_COLORS[f.subtype] || '#888';

    const plateR = iconSize * 0.55;
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1.5;
    roundRect(ctx, x - plateR, y - plateR, plateR * 2, plateR * 2 + Math.max(10, ps(4)), 4);
    ctx.fill();
    ctx.stroke();

    ctx.font = `${iconSize}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ICONS[f.subtype] || '📦', x, y);

    ctx.font = labelFont;
    ctx.fillStyle = borderColor;
    ctx.textBaseline = 'top';
    ctx.fillText(LABELS[f.subtype] || f.subtype, x, y + plateR - 2);
  }
}

function drawMaterialStacks(ctx: CanvasRenderingContext2D, materials: AssetUpdate[]) {
  const iconSize = Math.max(14, ps(7));
  const labelFont = `600 ${Math.max(6, ps(2))}px 'JetBrains Mono', monospace`;

  const ICONS: Record<string, string> = {
    rebar: '🪨',
    conduit: '🔌',
    drywall: '🧱',
    concrete: '🪣',
  };
  const LABELS: Record<string, string> = {
    rebar: 'REBAR',
    conduit: 'CONDUIT',
    drywall: 'DRYWALL',
    concrete: 'CONCRETE',
  };

  for (const m of materials) {
    const x = px(m.x);
    const y = py(m.y);

    ctx.font = `${iconSize}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ICONS[m.subtype] || '📦', x, y);

    ctx.font = labelFont;
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.textBaseline = 'top';
    ctx.fillText(LABELS[m.subtype] || m.subtype, x, y + iconSize * 0.45);
  }
}

function drawHeatmap(ctx: CanvasRenderingContext2D, trails: Trail, sw: number, sh: number) {
  const cellSize = 5;
  const cols = Math.ceil(sw / cellSize);
  const rows = Math.ceil(sh / cellSize);
  const grid = new Float32Array(cols * rows);
  let maxVal = 0;

  for (const positions of Object.values(trails)) {
    for (const [ppx, ppy] of positions) {
      const col = Math.floor(ppx / cellSize);
      const row = Math.floor(ppy / cellSize);
      if (col >= 0 && col < cols && row >= 0 && row < rows) {
        grid[row * cols + col] += 1;
        maxVal = Math.max(maxVal, grid[row * cols + col]);
      }
    }
  }
  if (maxVal === 0) return;

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const v = grid[r * cols + c];
      if (v === 0) continue;
      const norm = v / maxVal;
      if (norm < 0.1) continue;
      if (norm > 0.5) {
        ctx.fillStyle = `rgba(220,38,38,${norm * 0.25})`;
      } else {
        ctx.fillStyle = `rgba(234,179,8,${norm * 0.2})`;
      }
      ctx.fillRect(px(c * cellSize), py(r * cellSize), ps(cellSize), ps(cellSize));
    }
  }
}

function drawRecommendationArrows(ctx: CanvasRenderingContext2D, recs: Recommendation[]) {
  for (const rec of recs) {
    if (rec.applied || !rec.to_position) continue;
    const x1 = px(rec.from_position.x);
    const y1 = py(rec.from_position.y);
    const x2 = px(rec.to_position.x);
    const y2 = py(rec.to_position.y);

    ctx.strokeStyle = 'rgba(234,88,12,0.15)';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
    ctx.stroke();

    ctx.strokeStyle = '#ea580c';
    ctx.lineWidth = 2;
    ctx.setLineDash([7, 4]);
    ctx.beginPath();
    ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.setLineDash([]);

    const angle = Math.atan2(y2 - y1, x2 - x1);
    ctx.fillStyle = '#ea580c';
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - 9 * Math.cos(angle - 0.35), y2 - 9 * Math.sin(angle - 0.35));
    ctx.lineTo(x2 - 9 * Math.cos(angle + 0.35), y2 - 9 * Math.sin(angle + 0.35));
    ctx.closePath();
    ctx.fill();

    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2 - 10;
    const text = `€${Math.round(rec.daily_savings)}/day`;
    ctx.font = `700 9px 'JetBrains Mono', monospace`;
    const tw = ctx.measureText(text).width;
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    roundRect(ctx, mx - tw / 2 - 4, my - 7, tw + 8, 14, 3);
    ctx.fill();
    ctx.strokeStyle = '#ea580c';
    ctx.lineWidth = 1;
    roundRect(ctx, mx - tw / 2 - 4, my - 7, tw + 8, 14, 3);
    ctx.stroke();
    ctx.fillStyle = '#ea580c';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, mx, my);
  }
}

function drawScaleBar(ctx: CanvasRenderingContext2D, cw: number, ch: number) {
  const barLen = ps(20);
  const x = cw - barLen - 16;
  const y = ch - 14;

  ctx.strokeStyle = 'rgba(0,0,0,0.3)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, y); ctx.lineTo(x + barLen, y);
  ctx.moveTo(x, y - 3); ctx.lineTo(x, y + 3);
  ctx.moveTo(x + barLen, y - 3); ctx.lineTo(x + barLen, y + 3);
  ctx.stroke();
  ctx.fillStyle = 'rgba(0,0,0,0.4)';
  ctx.font = "500 8px 'JetBrains Mono', monospace";
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText('20m', x + barLen / 2, y - 4);
}

function drawLegend(ctx: CanvasRenderingContext2D, cw: number) {
  const lx = cw - 96;
  let ly = 8;
  const dot = 5;

  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  roundRect(ctx, lx - 6, ly - 4, 100, 100, 4);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.1)';
  ctx.lineWidth = 1;
  roundRect(ctx, lx - 6, ly - 4, 100, 100, 4);
  ctx.stroke();

  ctx.font = '8px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';

  const trades: [string, string][] = [
    ['Structural', TRADE_COLORS.structural],
    ['MEP', TRADE_COLORS.mep],
    ['Finishing', TRADE_COLORS.finishing],
    ['General', TRADE_COLORS.general],
  ];

  for (const [label, color] of trades) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(lx + dot / 2, ly + dot, dot / 2 + 0.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillText(label, lx + dot + 5, ly + dot);
    ly += 14;
  }

  ly += 4;
  ctx.fillStyle = '#16a34a';
  ctx.fillRect(lx, ly, dot, dot);
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillText('Active', lx + dot + 5, ly + dot / 2);
  ly += 14;
  ctx.strokeStyle = '#dc2626';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(lx, ly, dot, dot);
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillText('Idle', lx + dot + 5, ly + dot / 2);
}

function drawSelectionHighlight(ctx: CanvasRenderingContext2D, assets: AssetUpdate[], selectedId: string) {
  const asset = assets.find(a => a.id === selectedId);
  if (!asset) return;

  const x = px(asset.x);
  const y = py(asset.y);
  const t = performance.now() / 600;
  const pulse = 0.5 + 0.5 * Math.sin(t);
  const r = Math.max(12, ps(6)) + pulse * 4;

  // Outer pulsing ring
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(234, 88, 12, ${0.4 + pulse * 0.3})`;
  ctx.lineWidth = 2;
  ctx.stroke();

  // Inner ring
  ctx.beginPath();
  ctx.arc(x, y, r - 4, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(234, 88, 12, ${0.15 + pulse * 0.1})`;
  ctx.lineWidth = 1;
  ctx.stroke();

  // Label tooltip above
  const label = asset.id;
  ctx.font = `600 10px 'JetBrains Mono', monospace`;
  const tw = ctx.measureText(label).width;
  const tooltipX = x - tw / 2 - 6;
  const tooltipY = y - r - 18;

  ctx.fillStyle = 'rgba(0,0,0,0.75)';
  roundRect(ctx, tooltipX, tooltipY, tw + 12, 16, 4);
  ctx.fill();

  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x, tooltipY + 8);
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function hexToRgb(hex: string): [number, number, number] {
  if (hex.startsWith('#') && hex.length === 7) {
    return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  }
  return [148, 163, 184];
}
