import { useState } from 'react';
import { useAuth } from '../../lib/auth/AuthProvider';
import { recordApi } from '../../services/recordApi';
import RecordAsk from './RecordAsk';
import RecordCosts from './RecordCosts';
import RecordInbox from './RecordInbox';
import RecordLedger from './RecordLedger';
import RecordTimeline from './RecordTimeline';

type Tab = 'timeline' | 'inbox' | 'costs' | 'ledger' | 'ask';

const TABS: { id: Tab; label: string }[] = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'inbox', label: 'Inbox' },
  { id: 'costs', label: 'Costs' },
  { id: 'ledger', label: 'Ledger' },
  { id: 'ask', label: 'Ask' },
];

export default function RecordPage() {
  const { org } = useAuth();
  const role = org?.role ?? 'viewer';
  const canWrite = role === 'owner' || role === 'admin' || role === 'member';
  const isAdmin = role === 'owner' || role === 'admin';

  const [tab, setTab] = useState<Tab>('timeline');
  const [refreshKey, setRefreshKey] = useState(0);
  const [captureText, setCaptureText] = useState('');
  const [capturing, setCapturing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const bump = () => setRefreshKey((k) => k + 1);

  const onCapture = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = captureText.trim();
    if (!text) return;
    setCapturing(true);
    setStatus(null);
    try {
      const r = await recordApi.capture(text);
      setCaptureText('');
      setStatus(`Captured ${r.events.length} observation(s) — review them in the Inbox.`);
      setTab('inbox');
      bump();
    } catch {
      setStatus('Capture failed.');
    } finally {
      setCapturing(false);
    }
  };

  const onGenerate = async () => {
    if (!confirm('Regenerate demo history? This replaces the existing record for this project.'))
      return;
    setGenerating(true);
    setStatus(null);
    try {
      const s = await recordApi.generateDemo();
      setStatus(`Generated ${s.event_count} events across ${s.days} days.`);
      bump();
    } catch {
      setStatus('Generation failed.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto">
      <div className="max-w-5xl mx-auto px-6 py-6">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight mb-1">System of record</h1>
            <p className="text-sm text-muted-foreground">
              The immutable, tamper-evident log of everything on site. Costs and reports are
              projections; cameras will feed the same ledger.
            </p>
          </div>
          {isAdmin && (
            <button
              onClick={onGenerate}
              disabled={generating}
              className="text-sm rounded-md border border-border px-3 py-1.5 hover:bg-secondary disabled:opacity-50 whitespace-nowrap"
            >
              {generating ? 'Generating…' : 'Generate demo data'}
            </button>
          )}
        </div>

        {canWrite && (
          <form onSubmit={onCapture} className="flex gap-2 mb-3">
            <input
              value={captureText}
              onChange={(e) => setCaptureText(e.target.value)}
              placeholder="Quick capture: e.g. '3 tonnes of rebar delivered to zone A'"
              className="flex-1 rounded-md border border-border bg-card px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={capturing}
              className="rounded-md bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:bg-primary/90 disabled:opacity-50 whitespace-nowrap"
            >
              {capturing ? 'Capturing…' : '+ Capture'}
            </button>
          </form>
        )}

        {status && (
          <div className="mb-3 text-sm text-muted-foreground bg-secondary rounded-md px-3 py-2">
            {status}
          </div>
        )}

        <div className="flex gap-1 border-b border-border mb-5">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={[
                'px-3 py-2 text-sm font-medium border-b-2 -mb-px',
                tab === t.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div>
          {tab === 'timeline' && <RecordTimeline refreshKey={refreshKey} />}
          {tab === 'inbox' && <RecordInbox canWrite={canWrite} onChanged={bump} />}
          {tab === 'costs' && <RecordCosts refreshKey={refreshKey} />}
          {tab === 'ledger' && <RecordLedger refreshKey={refreshKey} />}
          {tab === 'ask' && <RecordAsk />}
        </div>
      </div>
    </div>
  );
}
