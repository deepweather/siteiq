/**
 * Project list — the entry point for the editor.
 *
 * Layout:
 *  - "My projects" — org-owned, editable.
 *  - "Templates" — public stock seeds. Read-only here, but can be
 *    duplicated to make a new org-owned project.
 */
import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
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

export default function ProjectListPage() {
  const nav = useNavigate();
  const { org } = useAuth();
  const [items, setItems] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const onCreate = async () => {
    if (!isOwnerRole) return;
    const slug = window.prompt('Project slug (lowercase, dashes):');
    if (!slug) return;
    const name = window.prompt('Project name:', slug) ?? slug;
    try {
      const doc = blankProjectDocument(slug, name);
      // Seed with one zone so the editor opens with something on screen.
      doc.zones = [{
        id: 'z1', label: 'Zone 1', x: 10, y: 10, width: 60, height: 50,
        phase: 'structural', phase_progress: 0.5, level_id: 'L0',
      }];
      const detail = await createProject(doc, { message: 'Created from editor' });
      nav(`/app/projects/${detail.id}/edit`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'create failed');
    }
  };

  const onDuplicate = async (item: ProjectListItem) => {
    try {
      const src = await getProject(item.id);
      const slug = window.prompt('New slug:', `${item.slug}-copy`);
      if (!slug) return;
      const cloned: ProjectDocument = {
        ...src.document,
        slug,
        name: `${src.document.name} (copy)`,
      };
      const detail = await createProject(cloned, { message: 'Duplicated' });
      nav(`/app/projects/${detail.id}/edit`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'duplicate failed');
    }
  };

  const onActivate = async (item: ProjectListItem) => {
    await activateProject(item.id);
    nav('/app');
  };

  const mine = items.filter((p) => p.is_owner);
  const templates = items.filter((p) => !p.is_owner);

  return (
    <div className="min-h-screen bg-background">
      <header className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Projects</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Build your own site, or duplicate a template to start from.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/app"
            className="px-3 py-1.5 text-xs font-medium rounded border border-border hover:bg-secondary"
          >
            Back to dashboard
          </Link>
          {isOwnerRole && (
            <button
              type="button"
              onClick={onCreate}
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
        <Section title="My projects" empty={!loading && mine.length === 0 ? 'You have no custom projects yet.' : null}>
          {mine.map((p) => (
            <ProjectCard
              key={p.id}
              item={p}
              onOpen={() => nav(`/app/projects/${p.id}/edit`)}
              onActivate={() => onActivate(p)}
              onDuplicate={() => onDuplicate(p)}
            />
          ))}
        </Section>
        <Section title="Stock templates">
          {templates.map((p) => (
            <ProjectCard
              key={p.id}
              item={p}
              onActivate={() => onActivate(p)}
              onDuplicate={isOwnerRole ? () => onDuplicate(p) : undefined}
            />
          ))}
        </Section>
      </div>
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
    <div className="border border-border rounded-lg p-3 bg-card flex flex-col gap-2">
      <div>
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground truncate">{item.name}</h3>
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
            {item.discipline}
          </span>
        </div>
        <p className="text-xs text-muted-foreground line-clamp-2 mt-1">{item.description}</p>
      </div>
      <div className="text-[10px] text-muted-foreground font-mono mt-auto">
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
            className="flex-1 px-2 py-1 text-xs font-medium rounded border border-border hover:bg-secondary"
          >
            Activate
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
