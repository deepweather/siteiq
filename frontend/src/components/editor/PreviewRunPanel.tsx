/**
 * Preview Run panel — non-modal sidebar that surfaces the result of a
 * synchronous `POST /api/projects/{id}/preview` against the current
 * draft document. Closes when the document changes (so a stale preview
 * never claims to describe a doc that no longer exists) or via the
 * explicit close button.
 *
 * Kept deliberately distinct from the WasteReport component used in
 * the dashboard: that one consumes streaming WebSocket data and pairs
 * with `useAnimatedNumber`. The preview is a single shot — animation
 * would just delay the answer.
 */
import { useEffect, useState } from 'react';
import {
  previewProject,
  type PreviewResponse,
  type ProjectDocument,
} from '../../services/projectsApi';
import { formatCurrency, formatSimTime } from '../../utils/formatting';
import { ApiError } from '../../services/api';

interface PreviewRunPanelProps {
  projectId: string;
  document: ProjectDocument;
  /** Bump when the document mutates so the panel can auto-dismiss
   *  a stale preview. The hook treats any change as "different doc". */
  documentVersion: number;
  onClose: () => void;
}

export function PreviewRunPanel({ projectId, document, documentVersion, onClose }: PreviewRunPanelProps) {
  const [state, setState] = useState<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'error'; message: string; field?: string }
    | { kind: 'ready'; response: PreviewResponse; versionAtRun: number }
  >({ kind: 'idle' });

  // Fire on mount + whenever the user explicitly re-opens the panel.
  // The parent un-mounts + remounts to retrigger; we don't auto-refetch
  // on every keystroke because the simulation takes ~30 ms / call.
  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });
    previewProject(projectId, document)
      .then((response) => {
        if (cancelled) return;
        setState({ kind: 'ready', response, versionAtRun: documentVersion });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setState({ kind: 'error', message: e.message, field: e.field });
        } else {
          setState({ kind: 'error', message: e instanceof Error ? e.message : 'Preview failed' });
        }
      });
    return () => { cancelled = true; };
    // Intentionally don't depend on `document`: the first mount captures
    // the draft to run against, and a subsequent edit auto-dismisses
    // via the staleness check below rather than re-running on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Stale-document auto-dismiss: if the user edits after the preview
  // ran, the snapshot no longer describes what they're looking at —
  // close the panel rather than show misleading numbers.
  useEffect(() => {
    if (state.kind === 'ready' && documentVersion !== state.versionAtRun) {
      onClose();
    }
  }, [documentVersion, state, onClose]);

  return (
    <aside
      data-testid="preview-run-panel"
      className="w-72 shrink-0 border-l border-border bg-card overflow-y-auto"
    >
      <header className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Preview Run
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close preview"
          className="text-xs px-2 py-0.5 rounded hover:bg-secondary"
        >
          ×
        </button>
      </header>
      <div className="p-3 space-y-3 text-xs">
        {state.kind === 'loading' && <Loading />}
        {state.kind === 'error' && <ErrorBox message={state.message} field={state.field} />}
        {state.kind === 'ready' && <Result response={state.response} />}
      </div>
    </aside>
  );
}

function Loading() {
  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
      Running simulation…
    </div>
  );
}

function ErrorBox({ message, field }: { message: string; field?: string }) {
  return (
    <div className="border border-destructive/40 bg-destructive/5 rounded-md p-2 text-destructive">
      <div className="font-semibold text-[11px] uppercase">Preview failed</div>
      <p className="mt-1">{message}</p>
      {field && (
        <p className="mt-0.5 text-[10px] text-muted-foreground">field: {field}</p>
      )}
    </div>
  );
}

function Result({ response }: { response: PreviewResponse }) {
  const w = response.waste;
  const topRecs = response.recommendations.slice(0, 5);
  return (
    <>
      <div className="rounded-md bg-secondary/40 p-2">
        <div className="text-[10px] text-muted-foreground uppercase">Snapshot</div>
        <div className="mt-0.5 font-mono tabular-nums">
          Day {response.sim_day} · {formatSimTime(response.sim_time)}
        </div>
      </div>

      <section data-testid="preview-waste">
        <div className="text-[10px] text-muted-foreground uppercase mb-1">Recoverable waste</div>
        <div className="space-y-1">
          <Row label="Daily" value={formatCurrency(w.total_daily)} highlight />
          <Row label="Monthly" value={formatCurrency(w.total_monthly)} />
          <Row label="Toilet walks (daily)" value={formatCurrency(w.toilet_walk_daily)} />
          <Row label="Material handling (daily)" value={formatCurrency(w.material_handling_daily)} />
          <Row label="Equipment idle (daily)" value={formatCurrency(w.equipment_idle_daily)} />
          {w.vertical_transport_daily > 0 && (
            <Row label="Vertical transport (daily)" value={formatCurrency(w.vertical_transport_daily)} />
          )}
        </div>
      </section>

      <section data-testid="preview-recommendations">
        <div className="text-[10px] text-muted-foreground uppercase mb-1">
          Top recommendations ({topRecs.length} of {response.recommendations.length})
        </div>
        {topRecs.length === 0 ? (
          <p className="text-muted-foreground italic">No recommendations — this layout is already efficient.</p>
        ) : (
          <ul className="space-y-1.5">
            {topRecs.map((r) => (
              <li key={r.id} className="border border-border rounded p-1.5">
                <div className="font-medium text-foreground">{r.title}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">{r.description}</div>
                <div className="text-[10px] mt-0.5 font-mono tabular-nums text-success">
                  +{formatCurrency(r.monthly_savings)} / mo
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function Row({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`flex justify-between font-mono tabular-nums ${highlight ? 'text-foreground font-semibold' : 'text-muted-foreground'}`}>
      <span className={highlight ? 'font-sans font-normal' : 'font-sans'}>{label}</span>
      <span>{value}</span>
    </div>
  );
}
