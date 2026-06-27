import { useCallback, useEffect, useMemo, useState } from 'react';
import { recordApi, type SubjectRow } from '../../services/recordApi';
import { useEntityNav } from './entityNav';
import { subjectIcon, subjectTypeLabel } from './format';

/** Directory: a searchable, categorised roster of every subject on site
 *  (workers, equipment, materials, …). Clicking a card opens its full
 *  record in the shared drawer — the same surface every other tab links to. */
export default function RecordDirectory({ refreshKey }: { refreshKey: number }) {
  const openEntity = useEntityNav();
  const [subjects, setSubjects] = useState<SubjectRow[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [category, setCategory] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await recordApi.listSubjects();
      setSubjects(r.subjects);
      setCounts(r.counts);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const categories = useMemo(() => {
    const types = Object.keys(counts).sort((a, b) => (counts[b] ?? 0) - (counts[a] ?? 0));
    return ['all', ...types];
  }, [counts]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return subjects.filter((s) => {
      if (category !== 'all' && s.subject_type !== category) return false;
      if (!needle) return true;
      return (
        s.subject_id.toLowerCase().includes(needle) ||
        (s.descriptor ?? '').toLowerCase().includes(needle)
      );
    });
  }, [subjects, category, search]);

  return (
    <div className="space-y-4">
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search workers, equipment, materials, zones…"
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
      />
      <div className="flex flex-wrap gap-1.5">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={[
              'text-xs rounded-full px-2.5 py-1 border',
              category === c
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground hover:bg-secondary',
            ].join(' ')}
          >
            {c === 'all' ? `All (${subjects.length})` : subjectTypeLabel(c)}
            {c !== 'all' && <span className="ml-1 font-mono">{counts[c] ?? 0}</span>}
          </button>
        ))}
      </div>

      {loading && subjects.length === 0 ? (
        <div className="px-1 py-6 text-sm text-muted-foreground">Loading directory…</div>
      ) : filtered.length === 0 ? (
        <div className="px-1 py-10 text-center text-sm text-muted-foreground">
          {subjects.length === 0
            ? 'No record yet for this project. Generate demo data (above) or let the simulation run — entries appear automatically.'
            : 'No subjects match.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((s) => (
            <button
              key={`${s.subject_type}:${s.subject_id}`}
              onClick={() => openEntity(s.subject_type, s.subject_id)}
              data-testid="subject-card"
              className="text-left rounded-xl border border-border bg-card p-3 flex items-center gap-3 hover:border-primary/50 hover:bg-secondary/40 transition-colors"
            >
              <span className="text-xl shrink-0" aria-hidden="true">
                {subjectIcon(s.subject_type)}
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium truncate">{s.subject_id}</span>
                <span className="block text-[11px] text-muted-foreground truncate">
                  {s.descriptor ?? subjectTypeLabel(s.subject_type)}
                  {s.last_state ? ` · ${s.last_state}` : ''} · {s.event_count} evt
                </span>
              </span>
              {s.pending > 0 && (
                <span className="text-[10px] rounded bg-amber-100 text-amber-700 px-1.5 py-0.5 shrink-0">
                  {s.pending}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
