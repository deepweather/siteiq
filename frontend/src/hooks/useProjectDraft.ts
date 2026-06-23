/**
 * Editor state owned via `useReducer` so undo/redo is a single
 * action-history push. The reducer is pure — the autosave loop reads
 * the latest state and posts it to the backend with `If-Match` set
 * to the version id the editor loaded with.
 */
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
  type ProjectDocument,
  type ProjectDetail,
  type ValidationIssue,
  getProject,
  saveProject,
  validateProject,
} from '../services/projectsApi';
import { ApiError } from '../services/api';

const MAX_HISTORY = 50;
const AUTOSAVE_INTERVAL_MS = 5000;

type Action =
  | { type: 'set'; document: ProjectDocument }
  | { type: 'patch'; update: (doc: ProjectDocument) => ProjectDocument }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'mark-saved'; versionId: string };

interface DraftState {
  current: ProjectDocument | null;
  past: ProjectDocument[];
  future: ProjectDocument[];
  savedVersionId: string | null;
}

function reducer(state: DraftState, action: Action): DraftState {
  switch (action.type) {
    case 'set':
      return {
        current: action.document,
        past: [],
        future: [],
        savedVersionId: state.savedVersionId,
      };
    case 'patch': {
      if (!state.current) return state;
      const next = action.update(state.current);
      if (next === state.current) return state;
      return {
        current: next,
        past: [...state.past.slice(-MAX_HISTORY + 1), state.current],
        future: [],
        savedVersionId: state.savedVersionId,
      };
    }
    case 'undo': {
      if (!state.past.length || !state.current) return state;
      const prev = state.past[state.past.length - 1];
      return {
        current: prev,
        past: state.past.slice(0, -1),
        future: [state.current, ...state.future],
        savedVersionId: state.savedVersionId,
      };
    }
    case 'redo': {
      if (!state.future.length || !state.current) return state;
      const next = state.future[0];
      return {
        current: next,
        past: [...state.past, state.current],
        future: state.future.slice(1),
        savedVersionId: state.savedVersionId,
      };
    }
    case 'mark-saved':
      return { ...state, savedVersionId: action.versionId };
    default:
      return state;
  }
}

const initialState: DraftState = {
  current: null,
  past: [],
  future: [],
  savedVersionId: null,
};

export function useProjectDraft(projectId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState<boolean>(false);
  const inFlightRef = useRef<Promise<void> | null>(null);
  const lastSavedHashRef = useRef<string>('');

  // Load on mount / when the project id changes.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getProject(projectId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        dispatch({ type: 'set', document: d.document });
        dispatch({ type: 'mark-saved', versionId: d.current_version_id ?? '' });
        lastSavedHashRef.current = JSON.stringify(d.document);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : 'Failed to load project';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId]);

  // Live validation: fire as the document changes (debounced one second).
  useEffect(() => {
    if (!projectId || !state.current) return;
    const id = window.setTimeout(() => {
      validateProject(projectId, state.current!)
        .then((r) => setIssues(r.issues))
        .catch(() => { /* validation failures shouldn't block editing */ });
    }, 800);
    return () => window.clearTimeout(id);
  }, [projectId, state.current]);

  // Autosave loop. Pushes the current doc every AUTOSAVE_INTERVAL_MS if
  // dirty. Uses `If-Match` so two editors can't silently clobber each
  // other.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const id = window.setInterval(async () => {
      if (cancelled || !state.current || inFlightRef.current || conflict) return;
      const serialized = JSON.stringify(state.current);
      if (serialized === lastSavedHashRef.current) return;
      setSaving(true);
      inFlightRef.current = saveProject(
        projectId,
        state.current,
        state.savedVersionId,
        'autosave',
      )
        .then((d) => {
          if (cancelled) return;
          setDetail(d);
          dispatch({ type: 'mark-saved', versionId: d.current_version_id ?? '' });
          lastSavedHashRef.current = serialized;
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          if (e instanceof ApiError && e.code === 'version_conflict') {
            setConflict(true);
          } else {
            setError(e instanceof Error ? e.message : 'autosave failed');
          }
        })
        .finally(() => {
          if (!cancelled) setSaving(false);
          inFlightRef.current = null;
        });
    }, AUTOSAVE_INTERVAL_MS);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [projectId, state.current, state.savedVersionId, conflict]);

  const patch = useCallback(
    (update: (doc: ProjectDocument) => ProjectDocument) =>
      dispatch({ type: 'patch', update }),
    [],
  );
  const undo = useCallback(() => dispatch({ type: 'undo' }), []);
  const redo = useCallback(() => dispatch({ type: 'redo' }), []);

  /** Hard-reset to a fresh `ProjectDetail` returned by the server.
   *  Used by side-channel mutations (e.g. background image upload) that
   *  bump the project version outside the autosave loop. Clears
   *  undo/redo because the new version is the new ground truth. */
  const applyServerUpdate = useCallback((d: ProjectDetail) => {
    setDetail(d);
    dispatch({ type: 'set', document: d.document });
    dispatch({ type: 'mark-saved', versionId: d.current_version_id ?? '' });
    lastSavedHashRef.current = JSON.stringify(d.document);
    setConflict(false);
  }, []);

  return {
    detail,
    document: state.current,
    issues,
    loading,
    saving,
    error,
    conflict,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
    savedVersionId: state.savedVersionId,
    patch,
    undo,
    redo,
    applyServerUpdate,
  };
}
