import type { SiteEventDTO } from '../../services/recordApi';
import {
  fmtTime,
  kindIcon,
  kindLabel,
  sourceClasses,
  statusClasses,
  summarizeEvent,
} from './format';

interface Props {
  event: SiteEventDTO;
  showDate?: boolean;
  children?: React.ReactNode;
}

/** One ledger event rendered as a list row. Used by Timeline, Ledger, Inbox. */
export function EventRow({ event: e, showDate, children }: Props) {
  return (
    <div className="px-4 py-3 flex items-start gap-3" data-testid="event-row">
      <div className="text-lg leading-none mt-0.5" aria-hidden="true">
        {kindIcon(e.kind)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{kindLabel(e.kind)}</span>
          <span
            className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${sourceClasses(e.source)}`}
          >
            {e.source}
          </span>
          {e.status !== 'confirmed' && (
            <span
              className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${statusClasses(e.status)}`}
            >
              {e.status}
            </span>
          )}
          {e.confidence < 1 && (
            <span className="text-[10px] font-mono text-muted-foreground">
              {Math.round(e.confidence * 100)}%
            </span>
          )}
        </div>
        <div className="text-sm text-muted-foreground truncate">
          {summarizeEvent(e.kind, e.payload)}
        </div>
        <div className="text-[11px] font-mono text-muted-foreground/70 mt-0.5">
          #{e.seq} · {e.subject_type}:{e.subject_id} ·{' '}
          {showDate
            ? new Date(e.occurred_at).toLocaleString()
            : fmtTime(e.occurred_at)}
        </div>
      </div>
      {children && <div className="shrink-0 flex items-center gap-2">{children}</div>}
    </div>
  );
}

export default EventRow;
