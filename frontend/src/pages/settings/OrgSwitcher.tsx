import { useAuth } from '../../lib/auth/AuthProvider';
import { orgs } from '../../services/api';

export default function OrgSwitcher() {
  const { memberships, org, refresh } = useAuth();
  const switchTo = async (id: string) => {
    await orgs.switch(id);
    await refresh();
  };
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight mb-1">Workspaces</h1>
        <p className="text-sm text-muted-foreground">
          You belong to {memberships.length} workspace{memberships.length === 1 ? '' : 's'}.
        </p>
      </div>
      <div className="rounded-xl border border-border bg-card divide-y divide-border">
        {memberships.map((m) => (
          <div key={m.id} className="px-5 py-4 flex items-center gap-4">
            <div className="flex-1">
              <div className="font-medium flex items-center gap-2">
                {m.name}
                {m.id === org?.id && (
                  <span className="text-xs uppercase tracking-wide bg-primary/10 text-primary px-2 py-0.5 rounded">
                    active
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">
                {m.role} · {m.plan}
              </div>
            </div>
            <button
              disabled={m.id === org?.id}
              onClick={() => switchTo(m.id)}
              className="text-sm font-medium rounded-md border border-border px-3 py-1.5 hover:bg-muted disabled:opacity-40"
            >
              Switch
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
