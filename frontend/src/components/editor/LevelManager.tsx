import { useRef, useState } from 'react';
import {
  deleteLevelBackground,
  getProject,
  type ProjectDetail,
  type ProjectDocument,
  type ProjectLevel,
  uploadLevelBackground,
} from '../../services/projectsApi';
import { ApiError } from '../../services/api';

interface LevelManagerProps {
  document: ProjectDocument;
  activeLevel: string;
  onActiveLevelChange: (id: string) => void;
  patch: (update: (doc: ProjectDocument) => ProjectDocument) => void;
  /** When the editor knows its project id + current saved version,
   *  the level rows can offer a background-image upload button. The
   *  upload is a side-channel save (POST writes a new version on the
   *  server) so the caller must apply the resulting detail back into
   *  the draft. Omitting these props hides the button. */
  projectId?: string;
  savedVersionId?: string | null;
  onProjectUpdated?: (detail: ProjectDetail) => void;
}

export function LevelManager({
  document, activeLevel, onActiveLevelChange, patch,
  projectId, savedVersionId, onProjectUpdated,
}: LevelManagerProps) {
  const sorted = [...document.levels].sort((a, b) => b.order - a.order);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleUpload = async (levelId: string, file: File) => {
    if (!projectId) return;
    setUploadError(null);
    try {
      await uploadLevelBackground(projectId, levelId, file, savedVersionId ?? null);
      // Re-fetch the full project so the new version + url land in the
      // draft via `applyServerUpdate`. We could merge in-place but the
      // round-trip keeps a single source of truth.
      const fresh = await getProject(projectId);
      onProjectUpdated?.(fresh);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : 'Upload failed');
    }
  };

  const handleClear = async (levelId: string) => {
    if (!projectId) return;
    setUploadError(null);
    try {
      await deleteLevelBackground(projectId, levelId);
      const fresh = await getProject(projectId);
      onProjectUpdated?.(fresh);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : 'Delete failed');
    }
  };

  const addLevel = () => {
    const highest = sorted[0];
    const nextOrder = (highest?.order ?? -1) + 1;
    const id = `L${nextOrder}`;
    const name = nextOrder === 0 ? 'EG' : nextOrder > 0 ? `${nextOrder}. OG` : `UG${-nextOrder}`;
    patch((d) => ({
      ...d,
      levels: [
        ...d.levels,
        { id, name, elevation_m: nextOrder * 3.5, order: nextOrder },
      ],
    }));
  };

  const removeLevel = (id: string) => {
    if (document.levels.length <= 1) return;
    if (id === 'L0') return; // protected
    if (!window.confirm('Remove this level? All zones/assets pinned to it will become invalid.')) return;
    patch((d) => ({ ...d, levels: d.levels.filter((lv) => lv.id !== id) }));
    if (activeLevel === id) onActiveLevelChange('L0');
  };

  const renameLevel = (id: string, name: string) => {
    patch((d) => ({
      ...d,
      levels: d.levels.map((lv) => (lv.id === id ? { ...lv, name } : lv)),
    }));
  };

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-2 py-1.5 bg-secondary flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Levels</span>
        <button
          type="button"
          onClick={addLevel}
          className="text-xs font-medium px-2 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
          title="Add level above the current top"
        >
          + Add
        </button>
      </div>
      <div className="divide-y divide-border">
        {sorted.map((lv) => (
          <LevelRow
            key={lv.id}
            level={lv}
            active={lv.id === activeLevel}
            removable={lv.id !== 'L0' && document.levels.length > 1}
            onSelect={() => onActiveLevelChange(lv.id)}
            onRename={(name) => renameLevel(lv.id, name)}
            onRemove={() => removeLevel(lv.id)}
            canUploadBackground={!!projectId}
            hasBackground={!!lv.background_image_url}
            onUpload={(file) => handleUpload(lv.id, file)}
            onClearBackground={() => handleClear(lv.id)}
          />
        ))}
      </div>
      {uploadError && (
        <div className="px-2 py-1 bg-destructive/10 text-destructive text-[10px]">
          {uploadError}
        </div>
      )}
    </div>
  );
}

function LevelRow({ level, active, removable, onSelect, onRename, onRemove,
                   canUploadBackground, hasBackground, onUpload, onClearBackground }: {
  level: ProjectLevel;
  active: boolean;
  removable: boolean;
  onSelect: () => void;
  onRename: (name: string) => void;
  onRemove: () => void;
  canUploadBackground: boolean;
  hasBackground: boolean;
  onUpload: (file: File) => void;
  onClearBackground: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1.5 ${active ? 'bg-primary/10' : ''}`}>
      <button
        type="button"
        onClick={onSelect}
        className="font-mono text-[10px] opacity-70 w-6 text-right tabular-nums"
      >
        {level.order >= 0 ? `+${level.order}` : level.order}
      </button>
      <input
        type="text"
        value={level.name}
        onChange={(e) => onRename(e.target.value)}
        className="flex-1 text-xs bg-transparent border-0 focus:ring-1 focus:ring-primary px-1 py-0.5 rounded"
      />
      {canUploadBackground && (
        <>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            data-testid={`level-bg-input-${level.id}`}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              // Reset so picking the same file twice retriggers onChange.
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title={hasBackground ? 'Replace floor-plan background' : 'Upload floor-plan background'}
            aria-label={`Upload background for ${level.name}`}
            className={
              'text-xs px-1.5 py-0.5 rounded hover:bg-secondary ' +
              (hasBackground ? 'text-primary' : 'text-muted-foreground')
            }
          >
            📐
          </button>
          {hasBackground && (
            <button
              type="button"
              onClick={onClearBackground}
              title="Remove floor-plan background"
              aria-label={`Remove background for ${level.name}`}
              className="text-[10px] text-muted-foreground hover:text-destructive px-1 rounded"
            >
              clr
            </button>
          )}
        </>
      )}
      {removable && (
        <button
          type="button"
          onClick={onRemove}
          title="Remove level"
          className="text-xs text-destructive hover:bg-destructive/10 px-1.5 py-0.5 rounded"
        >
          ×
        </button>
      )}
    </div>
  );
}
