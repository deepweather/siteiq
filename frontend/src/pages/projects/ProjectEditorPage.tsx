/**
 * Project editor.
 *
 * Layout:
 *  - Left sidebar: tool palette + level manager.
 *  - Centre: editor canvas.
 *  - Right sidebar: properties panel + validation issues.
 *  - Top bar: project name + save status + activate-now button.
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useProjectDraft } from '../../hooks/useProjectDraft';
import { activateProject, type ProjectDocument } from '../../services/projectsApi';
import { LevelManager } from '../../components/editor/LevelManager';
import { ToolPalette, type EditorTool } from '../../components/editor/ToolPalette';
import { PropertiesPanel, type EditorSelection } from '../../components/editor/PropertiesPanel';
import { EditorCanvas } from '../../components/editor/EditorCanvas';
import { ValidationOverlay } from '../../components/editor/ValidationOverlay';
import { PreviewRunPanel } from '../../components/editor/PreviewRunPanel';
import { ScheduleEditor } from '../../components/editor/ScheduleEditor';

const DEFAULT_LEVEL_ID = 'L0';

const TOOL_TO_FACILITY: Record<string, string | null> = {
  'add-toilet': 'toilet',
  'add-breakroom': 'breakroom',
  'add-office': 'office',
  'add-toolcrib': 'toolcrib',
};
const TOOL_TO_EQUIPMENT: Record<string, string | null> = {
  'add-crane': 'tower_crane',
  'add-pump': 'concrete_pump',
  'add-excavator': 'excavator',
  'add-sheet-pile': 'sheet_pile',
  // Dewatering pumps cycle through operate/idle states (handled by
  // `tiefbau_behavior.update_tiefbau_equipment`), so they live in the
  // `equipment` list — not `facilities`. The seed (munich-sewer.json)
  // already puts them there; the editor must match.
  'add-dewatering-pump': 'dewatering_pump',
};

export default function ProjectEditorPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const draft = useProjectDraft(id ?? null);
  const [tool, setTool] = useState<EditorTool>('select');
  const [activeLevel, setActiveLevel] = useState<string>(DEFAULT_LEVEL_ID);
  const [selection, setSelection] = useState<EditorSelection>(null);
  // Mount-key for the preview panel. Bumping forces a fresh
  // `<PreviewRunPanel>` instance (and thus a fresh API call). Null
  // means the panel is closed.
  const [previewKey, setPreviewKey] = useState<number | null>(null);
  const [rightTab, setRightTab] = useState<'properties' | 'schedule'>('properties');
  // Stale-detection counter for the preview panel: bumps once per
  // distinct `draft.document` reference. The panel captures this value
  // when its run completes and auto-dismisses when it diverges later.
  // Tracked as state (+ useEffect) rather than a ref so the React
  // Compiler can see the read site as pure.
  const [docVersion, setDocVersion] = useState(0);
  useEffect(() => {
    setDocVersion((v) => v + 1);
  }, [draft.document]);

  // Always default the active level to one that exists in the document.
  useEffect(() => {
    if (!draft.document) return;
    if (!draft.document.levels.some((lv) => lv.id === activeLevel)) {
      setActiveLevel(draft.document.levels[0]?.id ?? DEFAULT_LEVEL_ID);
    }
  }, [draft.document, activeLevel]);

  const onPlace = (pos: { x: number; y: number }) => {
    if (!draft.document) return;
    if (tool === 'add-zone') {
      draft.patch((d) => {
        const id = nextId(d.zones, 'z');
        return {
          ...d,
          zones: [
            ...d.zones,
            {
              id, label: `Zone ${d.zones.length + 1}`,
              x: Math.max(0, pos.x - 15), y: Math.max(0, pos.y - 15),
              width: 30, height: 30,
              phase: 'structural', phase_progress: 0.5,
              level_id: activeLevel,
            },
          ],
        };
      });
      return;
    }
    if (tool === 'add-stair' || tool === 'add-elevator') {
      // For multi-level connections, only the *current* level is the
      // first node. The user can extend `nodes` from the properties
      // panel for now. (Multi-level wizards are Phase 9 polish.)
      draft.patch((d) => {
        const id = nextId(d.connections, tool === 'add-stair' ? 'stair' : 'lift');
        const kind = tool === 'add-stair' ? 'stair' : 'elevator';
        const otherLevel = d.levels.find((lv) => lv.id !== activeLevel)?.id;
        const nodes = otherLevel
          ? [{ level_id: activeLevel, x: pos.x, y: pos.y }, { level_id: otherLevel, x: pos.x, y: pos.y }]
          : [{ level_id: activeLevel, x: pos.x, y: pos.y }];
        return { ...d, connections: [...d.connections, { id, kind, nodes }] };
      });
      return;
    }
    const facilitySub = TOOL_TO_FACILITY[tool];
    if (facilitySub) {
      draft.patch((d) => {
        const id = nextId(d.facilities, facilitySub);
        return {
          ...d,
          facilities: [...d.facilities, { id, subtype: facilitySub, x: pos.x, y: pos.y, level_id: activeLevel }],
        };
      });
      return;
    }
    const equipmentSub = TOOL_TO_EQUIPMENT[tool];
    if (equipmentSub) {
      draft.patch((d) => {
        const id = nextId(d.equipment, equipmentSub);
        return {
          ...d,
          equipment: [...d.equipment, {
            id, subtype: equipmentSub, x: pos.x, y: pos.y,
            state: 'operating', level_id: activeLevel,
          }],
        };
      });
      return;
    }
  };

  const onActivate = async () => {
    if (!id) return;
    await activateProject(id, draft.savedVersionId || undefined);
    nav('/app');
  };

  /** Commit a drag's final position to the document. One patch per
   *  drag → one undo step. */
  const onMoveSelection = (
    kind: 'zone' | 'facility' | 'equipment' | 'material' | 'connection',
    assetId: string,
    pos: { x: number; y: number },
  ) => {
    draft.patch((d) => {
      switch (kind) {
        case 'zone':
          return { ...d, zones: d.zones.map((z) => z.id === assetId ? { ...z, x: pos.x, y: pos.y } : z) };
        case 'facility':
          return { ...d, facilities: d.facilities.map((f) => f.id === assetId ? { ...f, x: pos.x, y: pos.y } : f) };
        case 'equipment':
          return { ...d, equipment: d.equipment.map((e) => e.id === assetId ? { ...e, x: pos.x, y: pos.y } : e) };
        case 'material':
          return { ...d, materials: d.materials.map((m) => m.id === assetId ? { ...m, x: pos.x, y: pos.y } : m) };
        case 'connection':
          // Move only this connection's anchor on the active level —
          // the other endpoints (on other levels) stay where they are.
          return {
            ...d,
            connections: d.connections.map((c) => {
              if (c.id !== assetId) return c;
              return {
                ...c,
                nodes: c.nodes.map((n) =>
                  n.level_id === activeLevel ? { ...n, x: pos.x, y: pos.y } : n,
                ),
              };
            }),
          };
        default:
          return d;
      }
    });
  };

  if (!id) return <div className="p-6 text-sm">No project id.</div>;
  if (draft.loading || !draft.document) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading project…
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      <header className="px-4 py-2.5 border-b border-border flex items-center gap-3 shrink-0">
        <Link to="/app/projects" className="text-xs px-2 py-1 rounded border border-border hover:bg-secondary">
          ← Projects
        </Link>
        <input
          type="text"
          value={draft.document.name}
          onChange={(e) => draft.patch((d) => ({ ...d, name: e.target.value }))}
          className="flex-1 text-sm font-semibold bg-transparent border-0 focus:ring-1 focus:ring-primary px-1 py-0.5 rounded"
        />
        <span className="text-[10px] text-muted-foreground font-mono">
          {draft.saving ? 'Saving…' : draft.conflict ? '⚠ conflict — reload' : 'Saved'}
        </span>
        <button
          type="button"
          onClick={draft.undo}
          disabled={!draft.canUndo}
          className="text-xs px-2 py-1 rounded border border-border hover:bg-secondary disabled:opacity-40"
        >Undo</button>
        <button
          type="button"
          onClick={draft.redo}
          disabled={!draft.canRedo}
          className="text-xs px-2 py-1 rounded border border-border hover:bg-secondary disabled:opacity-40"
        >Redo</button>
        <button
          type="button"
          onClick={() => setPreviewKey((k) => (k ?? 0) + 1)}
          className="text-xs px-3 py-1 rounded border border-border hover:bg-secondary font-medium"
          title="Run a transient simulation without activating this draft"
        >
          Preview Run
        </button>
        <button
          type="button"
          onClick={onActivate}
          className="text-xs px-3 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 font-semibold"
        >
          Activate
        </button>
      </header>
      {draft.error && (
        <div className="px-4 py-1 bg-destructive/10 text-destructive text-xs">{draft.error}</div>
      )}
      <div className="flex-1 flex min-h-0">
        <aside className="w-56 shrink-0 border-r border-border p-2 space-y-2 overflow-y-auto">
          <ToolPalette tool={tool} onChange={setTool} />
          <LevelManager
            document={draft.document}
            activeLevel={activeLevel}
            onActiveLevelChange={setActiveLevel}
            patch={draft.patch}
            projectId={id}
            savedVersionId={draft.savedVersionId}
            onProjectUpdated={draft.applyServerUpdate}
          />
          <SiteSizeEditor document={draft.document} patch={draft.patch} />
        </aside>
        <EditorCanvas
          document={draft.document}
          activeLevel={activeLevel}
          tool={tool}
          selection={selection}
          onSelect={setSelection}
          onPlace={onPlace}
          onMoveSelection={onMoveSelection}
        />
        <aside className="w-72 shrink-0 border-l border-border flex flex-col">
          <div className="flex shrink-0 border-b border-border">
            <RightTab active={rightTab === 'properties'} onClick={() => setRightTab('properties')}>
              Properties
            </RightTab>
            <RightTab active={rightTab === 'schedule'} onClick={() => setRightTab('schedule')}>
              Schedule
            </RightTab>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {rightTab === 'properties' ? (
              <>
                <PropertiesPanel
                  document={draft.document}
                  selection={selection}
                  patch={draft.patch}
                />
                <ValidationOverlay issues={draft.issues} />
              </>
            ) : (
              <ScheduleEditor document={draft.document} patch={draft.patch} />
            )}
          </div>
        </aside>
        {previewKey !== null && id && (
          <PreviewRunPanel
            key={previewKey}
            projectId={id}
            document={draft.document}
            documentVersion={docVersion}
            onClose={() => setPreviewKey(null)}
          />
        )}
      </div>
    </div>
  );
}

function RightTab({ active, onClick, children }: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'flex-1 text-[11px] py-1.5 font-medium border-b-2 ' +
        (active
          ? 'border-primary text-foreground bg-primary/5'
          : 'border-transparent text-muted-foreground hover:bg-secondary')
      }
    >
      {children}
    </button>
  );
}

function SiteSizeEditor({ document, patch }: {
  document: ProjectDocument;
  patch: (update: (doc: ProjectDocument) => ProjectDocument) => void;
}) {
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-2 py-1.5 bg-secondary text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Site
      </div>
      <div className="p-2 space-y-1.5">
        <Field label="Width (m)" value={document.width.toString()} type="number" onChange={(v) => patch((d) => ({ ...d, width: Number(v) }))} />
        <Field label="Height (m)" value={document.height.toString()} type="number" onChange={(v) => patch((d) => ({ ...d, height: Number(v) }))} />
        <Field label="Start day" value={document.start_day.toString()} type="number" onChange={(v) => patch((d) => ({ ...d, start_day: Number(v) }))} />
      </div>
    </div>
  );
}

function Field({ label, value, type = 'text', onChange }: { label: string; value: string; type?: 'text' | 'number'; onChange: (v: string) => void }) {
  return (
    <label className="block text-xs">
      <span className="text-muted-foreground text-[10px]">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-0.5 px-2 py-1 border border-border rounded bg-background text-xs"
      />
    </label>
  );
}

function nextId(list: { id: string }[], prefix: string): string {
  let i = 1;
  while (true) {
    const candidate = `${prefix}-${i}`;
    if (!list.some((x) => x.id === candidate)) return candidate;
    i += 1;
  }
}
