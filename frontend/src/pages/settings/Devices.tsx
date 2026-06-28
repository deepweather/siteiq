/** Settings -> Devices: fleet management. List devices with live health,
 *  provision new ones via a one-time claim code (+ QR + install one-liner),
 *  rename, rotate tokens, and revoke. Admin-gated server-side. */
import { useEffect, useState } from 'react';
import { ApiError } from '../../services/api';
import {
  devicesApi,
  type ClaimResult,
  type DeviceKind,
  type DeviceRow,
} from '../../services/devicesApi';

const KIND_ICON: Record<string, string> = { camera: '📷', gateway: '📡', sensor: '🔧' };
const HEALTH_TINT: Record<string, string> = {
  online: 'bg-success',
  offline: 'bg-destructive',
  never_seen: 'bg-muted-foreground',
};

export default function Devices() {
  const [rows, setRows] = useState<DeviceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setRows(await devicesApi.list());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load devices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = window.setInterval(load, 15000); // live health refresh
    return () => window.clearInterval(t);
  }, []);

  const onRevoke = async (d: DeviceRow) => {
    if (!confirm(`Revoke "${d.name}"? Its token stops working immediately.`)) return;
    await devicesApi.revoke(d.id);
    load();
  };
  const onRotate = async (d: DeviceRow) => {
    const res = await devicesApi.rotate(d.id);
    alert(`New token for "${d.name}" (copy now, shown once):\n\n${res.token}`);
    load();
  };
  const onRename = async (d: DeviceRow) => {
    const name = prompt('Rename device', d.name);
    if (name && name !== d.name) {
      await devicesApi.rename(d.id, name);
      load();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight mb-1">Devices</h1>
          <p className="text-sm text-muted-foreground">
            Cameras, gateways, and sensors that feed this workspace's ledger.
          </p>
        </div>
        <button
          onClick={() => setAdding(true)}
          className="text-sm rounded-md bg-primary text-primary-foreground px-3 py-1.5 font-medium"
        >
          Add device
        </button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="rounded-xl border border-border bg-card divide-y divide-border">
        {loading && rows.length === 0 ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">
            No devices yet. Add one to start ingesting real site data.
          </div>
        ) : (
          rows.map((d) => (
            <div key={d.id} className="px-5 py-4 flex items-center gap-4">
              <span className="text-2xl" aria-hidden>{KIND_ICON[d.kind] ?? '•'}</span>
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate flex items-center gap-2">
                  {d.name}
                  {d.status === 'revoked' ? (
                    <span className="text-xs uppercase tracking-wide bg-destructive/10 text-destructive px-2 py-0.5 rounded">
                      revoked
                    </span>
                  ) : null}
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                  <span className={`w-2 h-2 rounded-full ${HEALTH_TINT[d.health] ?? 'bg-muted-foreground'}`} />
                  {d.health.replace('_', ' ')}
                  {d.agent_version ? ` · v${d.agent_version}` : ''}
                  {` · ${d.events_total} events`}
                  {d.queue_depth ? ` · queue ${d.queue_depth}` : ''}
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <button onClick={() => onRename(d)} className="text-muted-foreground hover:text-foreground">Rename</button>
                {d.status !== 'revoked' ? (
                  <>
                    <button onClick={() => onRotate(d)} className="text-muted-foreground hover:text-foreground">Rotate</button>
                    <button onClick={() => onRevoke(d)} className="text-destructive hover:underline">Revoke</button>
                  </>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>

      {adding ? (
        <AddDeviceModal
          onClose={() => {
            setAdding(false);
            load();
          }}
        />
      ) : null}
    </div>
  );
}

function AddDeviceModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState<DeviceKind>('camera');
  const [claim, setClaim] = useState<ClaimResult | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      setClaim(await devicesApi.createClaim({ name: name.trim() || 'New device', kind }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-card rounded-2xl border border-border w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        {!claim ? (
          <>
            <h2 className="text-lg font-semibold mb-4">Add device</h2>
            <label className="block text-sm text-muted-foreground mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Tower Cam North"
              className="w-full rounded-md border border-border bg-background px-3 py-2 mb-4 outline-none focus:border-primary"
            />
            <label className="block text-sm text-muted-foreground mb-1">Kind</label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as DeviceKind)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 mb-6 outline-none focus:border-primary"
            >
              <option value="camera">Camera (edge CV)</option>
              <option value="gateway">Gateway (aggregates sensors)</option>
              <option value="sensor">Sensor</option>
            </select>
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-3 py-2 text-sm text-muted-foreground">Cancel</button>
              <button
                onClick={create}
                disabled={busy}
                className="px-4 py-2 text-sm rounded-md bg-primary text-primary-foreground font-medium disabled:opacity-50"
              >
                Create claim code
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 className="text-lg font-semibold mb-1">Claim "{claim.name}"</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Run this on the device. The code is shown once and expires.
            </p>
            <pre className="bg-background border border-border rounded-md p-3 text-xs overflow-x-auto whitespace-pre-wrap break-all mb-3 font-mono">
{`siteiq-agent claim \\
  --server ${window.location.origin} \\
  --code ${claim.code}`}
            </pre>
            <div className="text-xs text-muted-foreground mb-4">
              Project <span className="font-mono">{claim.project_id}</span> · kind{' '}
              <span className="font-mono">{claim.kind}</span> · expires{' '}
              {new Date(claim.expires_at).toLocaleString()}
            </div>
            <div className="flex justify-end">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm rounded-md bg-primary text-primary-foreground font-medium"
              >
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
