import { useEffect, useRef, useState } from 'react';
import { recordExportUrls } from '../../services/recordApi';

interface ExportItem {
  label: string;
  hint: string;
  href: string;
  managerOnly?: boolean;
}

/** Export dropdown for the record. Exporting requires member+ (the parent
 *  hides this for viewers); timesheets are manager-only. Links are
 *  `<a download>` so the browser saves the file with the auth cookie. */
export default function ExportMenu({ isManager }: { isManager: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, [open]);

  const items: ExportItem[] = [
    { label: 'Cost report', hint: 'CSV · billing / accounting', href: recordExportUrls.costsCsv() },
    { label: 'Event ledger', hint: 'CSV · spreadsheet', href: recordExportUrls.eventsCsv() },
    { label: 'Event ledger', hint: 'JSON · verifiable audit', href: recordExportUrls.eventsJson() },
    { label: 'Equipment utilization', hint: 'CSV · fleet / rental', href: recordExportUrls.equipmentCsv() },
    { label: 'Timesheets', hint: 'CSV · payroll', href: recordExportUrls.timesheetsCsv(), managerOnly: true },
  ];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-sm rounded-md border border-border px-3 py-1.5 hover:bg-secondary whitespace-nowrap"
      >
        Export ▾
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-64 rounded-xl border border-border bg-card shadow-lg z-20 py-1">
          {items
            .filter((it) => !it.managerOnly || isManager)
            .map((it) => (
              <a
                key={it.label + it.hint}
                href={it.href}
                download
                onClick={() => setOpen(false)}
                className="block px-3 py-2 hover:bg-secondary"
              >
                <span className="block text-sm font-medium">{it.label}</span>
                <span className="block text-[11px] text-muted-foreground">{it.hint}</span>
              </a>
            ))}
        </div>
      )}
    </div>
  );
}
