import { useEffect } from 'react';
import EntityDetail from './EntityDetail';

interface Props {
  subjectType: string;
  subjectId: string;
  onClose: () => void;
}

/** Slide-over drawer showing one entity's full record. Opened from any
 *  subject link across the Record page; closes on backdrop click or Esc. */
export function EntityDrawer({ subjectType, subjectId, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="flex-1 bg-black/30"
      />
      <div className="w-[520px] max-w-full bg-background border-l border-border shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            Entity record
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-muted-foreground hover:text-foreground rounded-md px-2 py-1 hover:bg-secondary"
          >
            Close ✕
          </button>
        </div>
        <div className="flex-1 overflow-auto p-5">
          <EntityDetail subjectType={subjectType} subjectId={subjectId} />
        </div>
      </div>
    </div>
  );
}

export default EntityDrawer;
