/** Editor properties panel — edits the currently selected asset.
 *
 * Selection is by `{ kind, id }` so we know which slice of the
 * document to mutate. Workers themselves are never edited directly;
 * the `worker_seeds` list is edited via the zone properties.
 */
import { type ProjectDocument } from '../../services/projectsApi';

export type EditorSelection =
  | { kind: 'zone'; id: string }
  | { kind: 'facility'; id: string }
  | { kind: 'equipment'; id: string }
  | { kind: 'material'; id: string }
  | { kind: 'connection'; id: string }
  | null;

interface PropertiesPanelProps {
  document: ProjectDocument;
  selection: EditorSelection;
  patch: (update: (doc: ProjectDocument) => ProjectDocument) => void;
}

export function PropertiesPanel({ document, selection, patch }: PropertiesPanelProps) {
  if (!selection) {
    return (
      <div className="border border-border rounded-lg p-3 text-xs text-muted-foreground italic">
        Select an item on the map to edit its properties.
      </div>
    );
  }

  if (selection.kind === 'zone') {
    const zone = document.zones.find((z) => z.id === selection.id);
    if (!zone) return <Stale />;
    return (
      <FieldList title={`Zone — ${zone.label}`}>
        <Field label="Label" value={zone.label} onChange={(v) => mutateZone(patch, zone.id, { label: v })} />
        <Field label="X" type="number" value={zone.x.toString()} onChange={(v) => mutateZone(patch, zone.id, { x: Number(v) })} />
        <Field label="Y" type="number" value={zone.y.toString()} onChange={(v) => mutateZone(patch, zone.id, { y: Number(v) })} />
        <Field label="Width" type="number" value={zone.width.toString()} onChange={(v) => mutateZone(patch, zone.id, { width: Number(v) })} />
        <Field label="Height" type="number" value={zone.height.toString()} onChange={(v) => mutateZone(patch, zone.id, { height: Number(v) })} />
        <SelectField
          label="Phase"
          value={zone.phase}
          options={[
            'excavation', 'shoring', 'piling', 'drainage',
            'foundation', 'structural', 'mep_roughin', 'closein',
            'finishes', 'paving', 'complete',
          ]}
          onChange={(v) => mutateZone(patch, zone.id, { phase: v })}
        />
        <Field label="Phase progress (0–1)" type="number" value={zone.phase_progress.toString()} onChange={(v) => mutateZone(patch, zone.id, { phase_progress: Number(v) })} />
        <WorkerSeedEditor document={document} zoneId={zone.id} patch={patch} />
      </FieldList>
    );
  }

  if (selection.kind === 'facility') {
    const f = document.facilities.find((x) => x.id === selection.id);
    if (!f) return <Stale />;
    return (
      <FieldList title={`Facility — ${f.id}`}>
        <Field label="Subtype" value={f.subtype} onChange={(v) => mutateFacility(patch, f.id, { subtype: v })} />
        <Field label="X" type="number" value={f.x.toString()} onChange={(v) => mutateFacility(patch, f.id, { x: Number(v) })} />
        <Field label="Y" type="number" value={f.y.toString()} onChange={(v) => mutateFacility(patch, f.id, { y: Number(v) })} />
        <LevelSelect document={document} value={f.level_id ?? 'L0'} onChange={(v) => mutateFacility(patch, f.id, { level_id: v })} />
        <DeleteButton onClick={() => deleteFacility(patch, f.id)} />
      </FieldList>
    );
  }

  if (selection.kind === 'equipment') {
    const e = document.equipment.find((x) => x.id === selection.id);
    if (!e) return <Stale />;
    return (
      <FieldList title={`Equipment — ${e.id}`}>
        <Field label="Subtype" value={e.subtype} onChange={(v) => mutateEquipment(patch, e.id, { subtype: v })} />
        <Field label="X" type="number" value={e.x.toString()} onChange={(v) => mutateEquipment(patch, e.id, { x: Number(v) })} />
        <Field label="Y" type="number" value={e.y.toString()} onChange={(v) => mutateEquipment(patch, e.id, { y: Number(v) })} />
        <SelectField label="State" value={e.state ?? 'operating'} options={['operating', 'idle']} onChange={(v) => mutateEquipment(patch, e.id, { state: v })} />
        <LevelSelect document={document} value={e.level_id ?? 'L0'} onChange={(v) => mutateEquipment(patch, e.id, { level_id: v })} />
        <DeleteButton onClick={() => deleteEquipment(patch, e.id)} />
      </FieldList>
    );
  }

  if (selection.kind === 'material') {
    const m = document.materials.find((x) => x.id === selection.id);
    if (!m) return <Stale />;
    return (
      <FieldList title={`Material — ${m.id}`}>
        <Field label="Subtype" value={m.subtype} onChange={(v) => mutateMaterial(patch, m.id, { subtype: v })} />
        <Field label="X" type="number" value={m.x.toString()} onChange={(v) => mutateMaterial(patch, m.id, { x: Number(v) })} />
        <Field label="Y" type="number" value={m.y.toString()} onChange={(v) => mutateMaterial(patch, m.id, { y: Number(v) })} />
        <Field label="Needed in zone" value={m.needed_in} onChange={(v) => mutateMaterial(patch, m.id, { needed_in: v })} />
        <LevelSelect document={document} value={m.level_id ?? 'L0'} onChange={(v) => mutateMaterial(patch, m.id, { level_id: v })} />
        <DeleteButton onClick={() => deleteMaterial(patch, m.id)} />
      </FieldList>
    );
  }

  if (selection.kind === 'connection') {
    const c = document.connections.find((x) => x.id === selection.id);
    if (!c) return <Stale />;
    return (
      <FieldList title={`${c.kind} — ${c.id}`}>
        <div className="text-xs text-muted-foreground">
          Touches: {c.nodes.map((n) => n.level_id).join(', ')}
        </div>
        {c.kind === 'elevator' && (
          <>
            <Field label="Capacity" type="number" value={(c.cab_capacity ?? 6).toString()} onChange={(v) => mutateConnection(patch, c.id, { cab_capacity: Number(v) })} />
            <Field label="Speed m/s" type="number" value={(c.speed_m_per_s ?? 1.5).toString()} onChange={(v) => mutateConnection(patch, c.id, { speed_m_per_s: Number(v) })} />
          </>
        )}
        <DeleteButton onClick={() => deleteConnection(patch, c.id)} />
      </FieldList>
    );
  }

  return null;
}

function Stale() {
  return <div className="text-xs text-muted-foreground italic">Selection no longer exists.</div>;
}

function FieldList({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-2 py-1.5 bg-secondary text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</div>
      <div className="p-2 space-y-1.5">{children}</div>
    </div>
  );
}

function Field({ label, value, type = 'text', onChange }: {
  label: string;
  value: string;
  type?: 'text' | 'number';
  onChange: (v: string) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="text-muted-foreground text-[10px]">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-0.5 px-2 py-1 border border-border rounded bg-background text-foreground text-xs focus:ring-1 focus:ring-primary outline-none"
      />
    </label>
  );
}

function SelectField({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="text-muted-foreground text-[10px]">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-0.5 px-2 py-1 border border-border rounded bg-background text-foreground text-xs focus:ring-1 focus:ring-primary outline-none"
      >
        {options.map((o) => (<option key={o} value={o}>{o}</option>))}
      </select>
    </label>
  );
}

function LevelSelect({ document, value, onChange }: {
  document: ProjectDocument;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <SelectField
      label="Level"
      value={value}
      options={document.levels.map((lv) => lv.id)}
      onChange={onChange}
    />
  );
}

function DeleteButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full px-2 py-1 text-xs font-medium rounded text-destructive hover:bg-destructive/10 border border-destructive/20"
    >
      Delete
    </button>
  );
}

function WorkerSeedEditor({ document, zoneId, patch }: {
  document: ProjectDocument;
  zoneId: string;
  patch: (update: (doc: ProjectDocument) => ProjectDocument) => void;
}) {
  const seeds = document.worker_seeds.filter((s) => s.zone_id === zoneId);
  const addSeed = () => {
    patch((d) => ({
      ...d,
      worker_seeds: [...d.worker_seeds, { zone_id: zoneId, trade: 'general', count: 4 }],
    }));
  };
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">Worker seeds</span>
        <button
          type="button"
          onClick={addSeed}
          className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-primary text-primary-foreground"
        >
          + Trade
        </button>
      </div>
      <div className="space-y-1 mt-1">
        {seeds.map((s, idx) => (
          <div key={`${s.trade}-${idx}`} className="flex gap-1">
            <input
              value={s.trade}
              onChange={(e) => updateSeed(patch, zoneId, idx, { trade: e.target.value })}
              className="flex-1 px-1.5 py-0.5 border border-border rounded bg-background text-xs"
            />
            <input
              type="number"
              value={s.count}
              onChange={(e) => updateSeed(patch, zoneId, idx, { count: Number(e.target.value) })}
              className="w-12 px-1.5 py-0.5 border border-border rounded bg-background text-xs"
            />
            <button
              type="button"
              onClick={() => removeSeed(patch, zoneId, idx)}
              className="px-1 text-destructive text-xs"
            >×</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Mutators ──────────────────────────────────────────────────────────


function mutateZone(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string, change: Partial<ProjectDocument['zones'][number]>) {
  patch((d) => ({ ...d, zones: d.zones.map((z) => z.id === id ? { ...z, ...change } : z) }));
}
function mutateFacility(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string, change: Partial<ProjectDocument['facilities'][number]>) {
  patch((d) => ({ ...d, facilities: d.facilities.map((f) => f.id === id ? { ...f, ...change } : f) }));
}
function deleteFacility(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string) {
  patch((d) => ({ ...d, facilities: d.facilities.filter((f) => f.id !== id) }));
}
function mutateEquipment(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string, change: Partial<ProjectDocument['equipment'][number]>) {
  patch((d) => ({ ...d, equipment: d.equipment.map((e) => e.id === id ? { ...e, ...change } : e) }));
}
function deleteEquipment(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string) {
  patch((d) => ({ ...d, equipment: d.equipment.filter((e) => e.id !== id) }));
}
function mutateMaterial(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string, change: Partial<ProjectDocument['materials'][number]>) {
  patch((d) => ({ ...d, materials: d.materials.map((m) => m.id === id ? { ...m, ...change } : m) }));
}
function deleteMaterial(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string) {
  patch((d) => ({ ...d, materials: d.materials.filter((m) => m.id !== id) }));
}
function mutateConnection(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string, change: Partial<ProjectDocument['connections'][number]>) {
  patch((d) => ({ ...d, connections: d.connections.map((c) => c.id === id ? { ...c, ...change } : c) }));
}
function deleteConnection(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, id: string) {
  patch((d) => ({ ...d, connections: d.connections.filter((c) => c.id !== id) }));
}
function updateSeed(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, zoneId: string, idx: number, change: Partial<ProjectDocument['worker_seeds'][number]>) {
  patch((d) => {
    const seedsForZone = d.worker_seeds
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => s.zone_id === zoneId);
    const target = seedsForZone[idx];
    if (!target) return d;
    return {
      ...d,
      worker_seeds: d.worker_seeds.map((s, i) => i === target.i ? { ...s, ...change } : s),
    };
  });
}
function removeSeed(patch: (update: (doc: ProjectDocument) => ProjectDocument) => void, zoneId: string, idx: number) {
  patch((d) => {
    const seedsForZone = d.worker_seeds
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => s.zone_id === zoneId);
    const target = seedsForZone[idx];
    if (!target) return d;
    return { ...d, worker_seeds: d.worker_seeds.filter((_, i) => i !== target.i) };
  });
}
