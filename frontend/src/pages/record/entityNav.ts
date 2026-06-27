import { createContext, useContext } from 'react';

/** Opens an entity's record (drawer) from anywhere in the Record page. */
export type OpenEntity = (subjectType: string, subjectId: string) => void;

// Default no-op so components using a subject link render safely outside the
// Record page (e.g. in isolated unit tests).
export const EntityNavContext = createContext<OpenEntity>(() => {});

export const useEntityNav = (): OpenEntity => useContext(EntityNavContext);

// Subject types that have no meaningful per-entity record to open.
const NON_NAVIGABLE = new Set(['site', 'event']);

export function isNavigableSubject(subjectType: string): boolean {
  return !NON_NAVIGABLE.has(subjectType);
}
