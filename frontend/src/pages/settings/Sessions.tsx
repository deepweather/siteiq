import { useEffect, useState } from 'react';
import { auth, type SessionRow } from '../../services/api';

export default function Sessions() {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setRows(await auth.listSessions());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onRevoke = async (id: string) => {
    await auth.revokeSession(id);
    load();
  };
  const onRevokeAll = async () => {
    if (!confirm('Sign out everywhere? You will stay signed in here.')) return;
    await auth.revokeAll();
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight mb-1">Active sessions</h1>
          <p className="text-sm text-muted-foreground">
            Each device that's signed in to SiteIQ shows up here.
          </p>
        </div>
        <button
          onClick={onRevokeAll}
          className="text-sm rounded-md border border-destructive text-destructive px-3 py-1.5 hover:bg-destructive/10"
        >
          Sign out everywhere
        </button>
      </div>
      <div className="rounded-xl border border-border bg-card divide-y divide-border">
        {loading ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">Loading…</div>
        ) : (
          rows.map((s) => (
            <div key={s.id} className="px-5 py-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate flex items-center gap-2">
                  {shortenUA(s.user_agent)}
                  {s.current && (
                    <span className="text-xs uppercase tracking-wide bg-primary/10 text-primary px-2 py-0.5 rounded">
                      this device
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground truncate">
                  {s.ip || 'unknown ip'} · last seen {new Date(s.last_seen_at).toLocaleString()}
                </div>
              </div>
              <button
                disabled={s.current}
                onClick={() => onRevoke(s.id)}
                className="text-sm text-destructive hover:underline disabled:opacity-40"
              >
                Revoke
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function shortenUA(ua: string): string {
  if (!ua) return 'Unknown device';
  if (ua.includes('Firefox')) return 'Firefox';
  if (ua.includes('Edg/')) return 'Edge';
  if (ua.includes('Chrome')) return 'Chrome';
  if (ua.includes('Safari')) return 'Safari';
  return ua.slice(0, 40);
}
