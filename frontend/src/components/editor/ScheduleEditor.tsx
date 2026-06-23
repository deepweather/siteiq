/**
 * Gantt-style schedule editor for the project editor.
 *
 * One row per zone (same order as LevelManager → site zones). Each
 * row is a horizontal track that hosts that zone's `ScheduleEntry`
 * blocks. The user can:
 *
 *   • drag a whole block horizontally to shift start/end together,
 *   • drag the left handle to move only `start_day`,
 *   • drag the right handle to move only `end_day`,
 *   • click "+ Phase" to append a new entry,
 *   • click "×" on a block to delete it.
 *
 * Coarse-grain undo: a single `patch` lands per drag, on mouseup —
 * not on every mousemove. Mirrors the EditorCanvas drag pattern.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ProjectDocument, ProjectScheduleEntry } from '../../services/projectsApi';
import { PHASE_COLORS, PHASE_LABELS } from '../../utils/colors';

// The phases the picker offers. Matches `models.site.Phase` minus the
// terminal "complete" state, which is implicit when a zone has no
// further scheduled work.
const PHASE_OPTIONS = [
  'excavation', 'shoring', 'piling', 'drainage',
  'foundation', 'structural', 'mep_roughin', 'closein',
  'finishes', 'paving',
] as const;

// Days of timeline padding past the latest end_day so the user can
// extend a block to the right without immediately running out of track.
const TIMELINE_TAIL_PAD_DAYS = 30;
const MIN_TIMELINE_DAYS = 60;

type DragMode = 'move' | 'resize-left' | 'resize-right';

interface DragState {
  zoneId: string;
  entryIndex: number;
  mode: DragMode;
  startClientX: number;
  rowWidthPx: number;
  totalDays: number;
  originalStart: number;
  originalEnd: number;
  // Live delta + flag that we crossed the click→drag threshold.
  daysDelta: number;
  moved: boolean;
}

const DRAG_THRESHOLD_PX = 3;

interface ScheduleEditorProps {
  document: ProjectDocument;
  patch: (update: (doc: ProjectDocument) => ProjectDocument) => void;
}

export function ScheduleEditor({ document, patch }: ScheduleEditorProps) {
  const dragRef = useRef<DragState | null>(null);
  // Live drag preview state mirroring the ref's `daysDelta`. Kept as
  // state (not just a ref) so the render path stays pure — the React
  // Compiler rejects ref reads during render. Updated by the window
  // mousemove handler on every drag tick, cleared on mouseup.
  const [liveDrag, setLiveDrag] = useState<{
    zoneId: string; entryIndex: number; mode: DragMode; daysDelta: number;
  } | null>(null);
  // Picker visibility — keyed by zone id so multiple zones don't share state.
  const [pickerZone, setPickerZone] = useState<string | null>(null);

  const totalDays = useMemo(() => {
    const maxEnd = document.schedule.reduce((m, s) => Math.max(m, s.end_day), 0);
    return Math.max(MIN_TIMELINE_DAYS, maxEnd + TIMELINE_TAIL_PAD_DAYS);
  }, [document.schedule]);

  // Window listeners for drag in progress. Identical pattern to
  // EditorCanvas: install once on mount, read from a ref.
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dxPx = e.clientX - d.startClientX;
      if (!d.moved && Math.abs(dxPx) > DRAG_THRESHOLD_PX) d.moved = true;
      if (d.moved) {
        const daysPerPx = d.totalDays / d.rowWidthPx;
        d.daysDelta = Math.round(dxPx * daysPerPx);
        setLiveDrag({
          zoneId: d.zoneId,
          entryIndex: d.entryIndex,
          mode: d.mode,
          daysDelta: d.daysDelta,
        });
      }
    };
    const onUp = () => {
      const d = dragRef.current;
      dragRef.current = null;
      if (d && d.moved) {
        commitDrag(d);
      }
      setLiveDrag(null);
    };
    const commitDrag = (d: DragState) => {
      patch((doc) => {
        const i = d.entryIndex;
        const entries = doc.schedule.filter((s) => s.zone_id === d.zoneId);
        if (i < 0 || i >= entries.length) return doc;
        const target = entries[i];
        // Find the matching global index — we filtered to a zone, so map back.
        let globalIdx = -1;
        let nthInZone = -1;
        for (let g = 0; g < doc.schedule.length; g++) {
          if (doc.schedule[g].zone_id === d.zoneId) {
            nthInZone += 1;
            if (nthInZone === i) { globalIdx = g; break; }
          }
        }
        if (globalIdx < 0) return doc;

        let nextStart = target.start_day;
        let nextEnd = target.end_day;
        if (d.mode === 'move') {
          nextStart = d.originalStart + d.daysDelta;
          nextEnd = d.originalEnd + d.daysDelta;
        } else if (d.mode === 'resize-left') {
          nextStart = d.originalStart + d.daysDelta;
        } else if (d.mode === 'resize-right') {
          nextEnd = d.originalEnd + d.daysDelta;
        }
        // Hard bounds: start_day ≥ 1, end_day ≥ start_day + 1.
        // We clamp end first so a left-handle drag can't shrink the
        // block to zero width.
        nextStart = Math.max(1, nextStart);
        nextEnd = Math.max(nextStart + 1, nextEnd);
        const updated = doc.schedule.map((s, gi) =>
          gi === globalIdx ? { ...s, start_day: nextStart, end_day: nextEnd } : s,
        );
        return { ...doc, schedule: updated };
      });
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [patch]);

  const startDrag = (
    e: React.MouseEvent,
    zoneId: string,
    entryIndex: number,
    mode: DragMode,
    rowEl: HTMLElement | null,
    entry: ProjectScheduleEntry,
  ) => {
    if (!rowEl) return;
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      zoneId,
      entryIndex,
      mode,
      startClientX: e.clientX,
      rowWidthPx: rowEl.getBoundingClientRect().width,
      totalDays,
      originalStart: entry.start_day,
      originalEnd: entry.end_day,
      daysDelta: 0,
      moved: false,
    };
    // Don't set liveDrag yet — the first mousemove past the 3px threshold
    // will. That preserves "click without drag" → no-op semantics.
  };

  const addPhase = (zoneId: string, phase: string) => {
    setPickerZone(null);
    patch((doc) => {
      const existing = doc.schedule.filter((s) => s.zone_id === zoneId);
      const currentMax = existing.reduce((m, s) => Math.max(m, s.end_day), 0);
      const startDay = (currentMax || 0) + 1;
      const newEntry: ProjectScheduleEntry = {
        zone_id: zoneId,
        phase,
        start_day: startDay,
        end_day: startDay + 30,
        trades_required: [],
      };
      return { ...doc, schedule: [...doc.schedule, newEntry] };
    });
  };

  const deleteEntry = (zoneId: string, entryIndex: number) => {
    patch((doc) => {
      let nthInZone = -1;
      const next = doc.schedule.filter((s) => {
        if (s.zone_id !== zoneId) return true;
        nthInZone += 1;
        return nthInZone !== entryIndex;
      });
      return { ...doc, schedule: next };
    });
  };

  // For paint we apply the in-flight drag delta to a derived copy of
  // each entry. This keeps `document.schedule` itself untouched until
  // mouseup, which is what gives us coarse-grain undo for free. Reads
  // come from `liveDrag` state so the render path is pure.
  const renderEntry = (zoneId: string, entryIndex: number, entry: ProjectScheduleEntry) => {
    if (!liveDrag || liveDrag.zoneId !== zoneId || liveDrag.entryIndex !== entryIndex) {
      return entry;
    }
    if (liveDrag.mode === 'move') {
      return { ...entry, start_day: entry.start_day + liveDrag.daysDelta, end_day: entry.end_day + liveDrag.daysDelta };
    }
    if (liveDrag.mode === 'resize-left') {
      return { ...entry, start_day: entry.start_day + liveDrag.daysDelta };
    }
    return { ...entry, end_day: entry.end_day + liveDrag.daysDelta };
  };

  if (document.zones.length === 0) {
    return (
      <div className="text-xs text-muted-foreground italic p-2">
        Add a zone to start scheduling.
      </div>
    );
  }

  return (
    <div data-testid="schedule-editor" className="space-y-2">
      <div className="px-1 text-[10px] text-muted-foreground">
        Drag block to shift · drag handles to resize · 1-day grid · click "×" to delete
      </div>
      {document.zones.map((zone) => {
        const entries = document.schedule
          .map((s, i) => ({ s, i }))
          .filter(({ s }) => s.zone_id === zone.id);
        return (
          <ScheduleRow
            key={zone.id}
            zoneId={zone.id}
            zoneLabel={zone.label}
            totalDays={totalDays}
            entries={entries.map(({ s }, idx) => ({ entry: s, indexInZone: idx, renderEntry: renderEntry(zone.id, idx, s) }))}
            onMoveStart={(idx, mode, e, rowEl, entry) => startDrag(e, zone.id, idx, mode, rowEl, entry)}
            onDelete={(idx) => deleteEntry(zone.id, idx)}
            picker={pickerZone === zone.id
              ? <PhasePicker onPick={(p) => addPhase(zone.id, p)} onCancel={() => setPickerZone(null)} />
              : null}
            onOpenPicker={() => setPickerZone(zone.id)}
          />
        );
      })}
    </div>
  );
}

interface ScheduleRowProps {
  zoneId: string;
  zoneLabel: string;
  totalDays: number;
  entries: { entry: ProjectScheduleEntry; indexInZone: number; renderEntry: ProjectScheduleEntry }[];
  onMoveStart: (entryIndex: number, mode: DragMode, e: React.MouseEvent, rowEl: HTMLElement | null, entry: ProjectScheduleEntry) => void;
  onDelete: (entryIndex: number) => void;
  picker: React.ReactNode;
  onOpenPicker: () => void;
}

function ScheduleRow({ zoneId, zoneLabel, totalDays, entries, onMoveStart, onDelete, picker, onOpenPicker }: ScheduleRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);
  return (
    <div data-testid={`schedule-row-${zoneId}`} className="flex items-center gap-2">
      <span className="w-20 text-xs text-muted-foreground shrink-0 truncate" title={zoneLabel}>
        {zoneLabel}
      </span>
      <div ref={rowRef} className="flex-1 relative h-7 bg-secondary/50 rounded">
        {entries.map(({ entry, indexInZone, renderEntry }) => {
          const left = (renderEntry.start_day / totalDays) * 100;
          const width = Math.max(0.5, ((renderEntry.end_day - renderEntry.start_day) / totalDays) * 100);
          return (
            <div
              key={`${zoneId}-${indexInZone}`}
              data-testid={`schedule-block-${zoneId}-${indexInZone}`}
              data-phase={renderEntry.phase}
              data-start-day={renderEntry.start_day}
              data-end-day={renderEntry.end_day}
              className="absolute top-0 h-full rounded text-[9px] text-white font-medium overflow-hidden flex items-center"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                backgroundColor: PHASE_COLORS[renderEntry.phase] ?? '#71717a',
                cursor: 'grab',
              }}
              onMouseDown={(e) => onMoveStart(indexInZone, 'move', e, rowRef.current, entry)}
              onContextMenu={(e) => { e.preventDefault(); onDelete(indexInZone); }}
              title={`${PHASE_LABELS[renderEntry.phase] ?? renderEntry.phase}: day ${renderEntry.start_day}–${renderEntry.end_day}`}
            >
              <span
                data-testid={`schedule-handle-left-${zoneId}-${indexInZone}`}
                className="w-1.5 h-full bg-black/30 cursor-ew-resize shrink-0"
                onMouseDown={(e) => onMoveStart(indexInZone, 'resize-left', e, rowRef.current, entry)}
              />
              <span className="px-1.5 flex-1 truncate select-none pointer-events-none">
                {PHASE_LABELS[renderEntry.phase] ?? renderEntry.phase}
              </span>
              <button
                type="button"
                data-testid={`schedule-delete-${zoneId}-${indexInZone}`}
                onClick={(e) => { e.stopPropagation(); onDelete(indexInZone); }}
                aria-label="Delete schedule entry"
                className="px-1 hover:bg-black/30"
              >
                ×
              </button>
              <span
                data-testid={`schedule-handle-right-${zoneId}-${indexInZone}`}
                className="w-1.5 h-full bg-black/30 cursor-ew-resize shrink-0"
                onMouseDown={(e) => onMoveStart(indexInZone, 'resize-right', e, rowRef.current, entry)}
              />
            </div>
          );
        })}
      </div>
      <div className="relative">
        <button
          type="button"
          data-testid={`schedule-add-${zoneId}`}
          onClick={onOpenPicker}
          className="text-[10px] font-medium px-2 py-0.5 rounded border border-border hover:bg-secondary"
        >
          + Phase
        </button>
        {picker}
      </div>
    </div>
  );
}

function PhasePicker({ onPick, onCancel }: { onPick: (p: string) => void; onCancel: () => void }) {
  return (
    <div
      data-testid="schedule-phase-picker"
      className="absolute right-0 top-6 z-10 bg-card border border-border rounded shadow-lg p-1 grid grid-cols-2 gap-1 min-w-[180px]"
    >
      {PHASE_OPTIONS.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onPick(p)}
          className="text-[10px] px-1.5 py-0.5 rounded hover:bg-secondary text-left"
          style={{ borderLeft: `3px solid ${PHASE_COLORS[p] ?? '#71717a'}` }}
        >
          {PHASE_LABELS[p] ?? p}
        </button>
      ))}
      <button
        type="button"
        onClick={onCancel}
        className="col-span-2 text-[10px] py-0.5 rounded hover:bg-secondary text-muted-foreground"
      >
        Cancel
      </button>
    </div>
  );
}
