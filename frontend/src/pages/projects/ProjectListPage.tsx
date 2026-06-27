/**
 * Project list — full-screen takeover with two sections:
 *   "My projects" — org-owned, editable.
 *   "Stock templates" — public seeds, read-only here. Duplicate to fork.
 *
 * Create + duplicate go through an inline modal so the flow works in
 * every browser context, no window.prompt().
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  type ProjectListItem,
  type ProjectDocument,
  listProjects,
  createProject,
  blankProjectDocument,
  activateProject,
  getProject,
} from '../../services/projectsApi';
import { useAuth } from '../../lib/auth/AuthProvider';
import { useLive } from '../../shell/useLive';

type ModalState =
  | { kind: 'new' }
  | { kind: 'duplicate'; source: ProjectListItem }
  | null;

export default function ProjectListPage() {
  const nav = useNavigate();
  const { org } = useAuth();
  const live = useLive();
  const [items, setItems] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    setLoading(true);
    listProjects()
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'failed'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  const isOwnerRole = org?.role === 'owner' || org?.role === 'admin';

  const onConfirmCreate = async (slug: string, name: string) => {
    setBusy(true);
    setError(null);
    try {
      const doc = blankProjectDocument(slug, name);
      doc.zones = [{
        id: 'z1', label: 'Zone 1', x: 10, y: 10, width: 60, height: 50,
        phase: 'structural', phase_progress: 0.5, level_id: 'L0',
      }];
      const detail = await createProject(doc, { message: 'Created from editor' });
      nav(`/app/projects/${detail.id}/edit`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'create failed');
    } finally {
      setBusy(false);
    }
  };

  const onConfirmDuplicate = async (source: ProjectListItem, slug: string, name: string) => {
    setBusy(true);
    setError(null);
    try {
      const src = await getProject(source.id);
      const cloned: ProjectDocument = { ...src.document, slug, name };
      const detail = await createProject(cloned, { message: `Duplicated from ${source.slug}` });
      nav(`/app/projects/${detail.id}/edit`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'duplicate failed');
    } finally {
      setBusy(false);
    }
  };

  const onActivate = async (item: ProjectListItem) => {
    if (item.is_active) {
      nav('/app');
      return;
    }
    setBusy(true);
    try {
      await activateProject(item.id);
      live.reload();
      nav('/app');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'activate failed');
      setBusy(false);
    }
  };

  const mine = items.filter((p) => p.is_owner);
  const templates = items.filter((p) => !p.is_owner);

  return (
    <div className="flex-1 overflow-y-auto bg-background">
      <header className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Projects</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Build your own site, or duplicate a template to start from.
          </p>
        </div>
        <div className="flex gap-2">
          {isOwnerRole && (
            <button
              type="button"
              onClick={() => setModal({ kind: 'new' })}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90"
            >
              + New project
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="px-6 py-2 text-xs text-destructive">{error}</div>
      )}

      <div className="px-6 py-6 max-w-6xl space-y-8">
        <Section
          title="My projects"
          empty={!loading && mine.length === 0 ? 'You have no custom projects yet — duplicate a template below to start.' : null}
        >
          {mine.map((p) => (
            <ProjectCard
              key={p.id}
              item={p}
              onOpen={() => nav(`/app/projects/${p.id}/edit`)}
              onActivate={() => onActivate(p)}
              onDuplicate={() => setModal({ kind: 'duplicate', source: p })}
            />
          ))}
        </Section>
        <Section title="Stock templates">
          {templates.map((p) => (
            <ProjectCard
              key={p.id}
              item={p}
              onActivate={() => onActivate(p)}
              onDuplicate={isOwnerRole ? () => setModal({ kind: 'duplicate', source: p }) : undefined}
            />
          ))}
        </Section>
      </div>

      {modal?.kind === 'new' && (
        <ProjectModal
          title="Create new project"
          submitLabel="Create"
          initialSlug=""
          initialName=""
          busy={busy}
          existingSlugs={items.map((p) => p.slug)}
          onCancel={() => setModal(null)}
          onSubmit={async (slug, name) => {
            await onConfirmCreate(slug, name);
            setModal(null);
          }}
        />
      )}
      {modal?.kind === 'duplicate' && (
        <ProjectModal
          title={`Duplicate "${modal.source.name}"`}
          submitLabel="Duplicate"
          initialSlug={uniqueSlug(`${modal.source.slug}-copy`, items.map((p) => p.slug))}
          initialName={`${modal.source.name} (copy)`}
          busy={busy}
          existingSlugs={items.map((p) => p.slug)}
          onCancel={() => setModal(null)}
          onSubmit={async (slug, name) => {
            await onConfirmDuplicate(modal.source, slug, name);
            setModal(null);
          }}
        />
      )}
    </div>
  );
}

function Section({ title, empty, children }: { title: string; empty?: string | null; children: React.ReactNode }) {
  const isEmpty = Array.isArray(children) ? children.length === 0 : !children;
  return (
    <section>
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
        {title}
      </h2>
      {isEmpty && empty ? (
        <div className="text-xs text-muted-foreground italic py-2">{empty}</div>
      ) : (
        <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">{children}</div>
      )}
    </section>
  );
}

function ProjectCard({ item, onOpen, onActivate, onDuplicate }: {
  item: ProjectListItem;
  onOpen?: () => void;
  onActivate?: () => void;
  onDuplicate?: () => void;
}) {
  return (
    <div className={`border rounded-lg p-3 bg-card flex flex-col gap-2 ${item.is_active ? 'border-primary/60 ring-1 ring-primary/20' : 'border-border'}`}>
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="text-sm font-semibold text-foreground truncate">{item.name}</h3>
          {item.is_active && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-success/15 text-success border border-success/30">
              <span className="w-1.5 h-1.5 rounded-full bg-success" />
              Active
            </span>
          )}
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider ml-auto">
            {item.discipline}
          </span>
        </div>
        <p className="text-xs text-muted-foreground line-clamp-2 mt-1">{item.description}</p>
      </div>
      <div className="text-[10px] text-muted-foreground font-mono mt-auto truncate">
        <code>{item.slug}</code>
        {item.current_version_id && (
          <span className="ml-2 opacity-60">v{item.current_version_id.slice(0, 8)}</span>
        )}
      </div>
      <div className="flex gap-1.5 mt-1">
        {onOpen && (
          <button
            type="button"
            onClick={onOpen}
            className="flex-1 px-2 py-1 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Edit
          </button>
        )}
        {onActivate && (
          <button
            type="button"
            onClick={onActivate}
            disabled={item.is_active}
            className={
              'flex-1 px-2 py-1 text-xs font-medium rounded border ' +
              (item.is_active
                ? 'border-border text-muted-foreground cursor-default opacity-60'
                : 'border-border hover:bg-secondary')
            }
            title={item.is_active ? 'Already running' : 'Pin the simulation to this project'}
          >
            {item.is_active ? 'Activated' : 'Activate'}
          </button>
        )}
        {onDuplicate && (
          <button
            type="button"
            onClick={onDuplicate}
            className="px-2 py-1 text-xs font-medium rounded border border-border hover:bg-secondary"
          >
            Duplicate
          </button>
        )}
      </div>
    </div>
  );
}

interface ProjectModalProps {
  title: string;
  submitLabel: string;
  initialSlug: string;
  initialName: string;
  busy: boolean;
  existingSlugs: string[];
  onCancel: () => void;
  onSubmit: (slug: string, name: string) => Promise<void>;
}

function ProjectModal({ title, submitLabel, initialSlug, initialName, busy, existingSlugs, onCancel, onSubmit }: ProjectModalProps) {
  const [slug, setSlug] = useState(initialSlug);
  const [name, setName] = useState(initialName);
  const [touched, setTouched] = useState({ slug: false, name: false });

  const slugValid = /^[a-z][a-z0-9-]*$/.test(slug);
  const slugTaken = existingSlugs.includes(slug);
  const nameValid = name.trim().length > 0;

  const slugError = (touched.slug || slug.length > 0)
    ? (!slugValid ? 'Use lowercase letters, digits and dashes (must start with a letter).'
      : slugTaken ? 'A project with that slug already exists.'
      : null)
    : null;
  const nameError = touched.name && !nameValid ? 'Project name is required.' : null;

  const canSubmit = slugValid && !slugTaken && nameValid && !busy;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    await onSubmit(slug.trim(), name.trim());
  };

  useEffect(() => {
    if (!name && slug) setName(slug);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="project-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-md bg-card border border-border rounded-xl shadow-xl"
      >
        <div className="px-5 pt-4 pb-3 border-b border-border">
          <h2 id="project-modal-title" className="text-base font-semibold text-foreground">{title}</h2>
          <p className="text-xs text-muted-foreground mt-1">
            The slug is a stable id used in URLs and the seed bundle — pick something short and unique.
          </p>
        </div>
        <div className="px-5 py-4 space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-foreground">Slug</span>
            <input
              autoFocus
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, slug: true }))}
              placeholder="my-new-site"
              className={`mt-1 w-full px-3 py-2 border rounded text-sm font-mono bg-background focus:ring-1 outline-none ${slugError ? 'border-destructive focus:ring-destructive' : 'border-border focus:ring-primary'}`}
            />
            {slugError && (
              <span className="text-[11px] text-destructive mt-1 block">{slugError}</span>
            )}
          </label>
          <label className="block">
            <span className="text-xs font-medium text-foreground">Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, name: true }))}
              placeholder="My New Site"
              className={`mt-1 w-full px-3 py-2 border rounded text-sm bg-background focus:ring-1 outline-none ${nameError ? 'border-destructive focus:ring-destructive' : 'border-border focus:ring-primary'}`}
            />
            {nameError && (
              <span className="text-[11px] text-destructive mt-1 block">{nameError}</span>
            )}
          </label>
        </div>
        <div className="px-5 py-3 border-t border-border flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-1.5 text-xs font-medium rounded border border-border hover:bg-secondary disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {busy ? 'Working…' : submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

function uniqueSlug(base: string, taken: string[]): string {
  if (!taken.includes(base)) return base;
  let i = 2;
  while (taken.includes(`${base}-${i}`)) i += 1;
  return `${base}-${i}`;
}
