/** Snap helpers shared by the editor canvas + its tests.
 *
 * Kept out of the component file so `react-refresh/only-export-components`
 * stays happy and HMR can preserve component state on edit.
 */

/** Snap a meter value to the nearest gridSize-meter multiple. gridSize=0 means snapping is off. */
export function snapToGrid(value: number, gridSize: number): number {
  if (gridSize <= 0) return value;
  return Math.round(value / gridSize) * gridSize;
}

/** Allowed grid step values, in meters. 0 means "off". Persisted in
 *  localStorage so the choice survives reloads. */
export const GRID_OPTIONS = [0, 1, 5, 10] as const;
export type GridSize = (typeof GRID_OPTIONS)[number];

export const GRID_STORAGE_KEY = 'siteiq.editor.grid_size';
export const DEFAULT_GRID: GridSize = 1;

export function loadInitialGrid(): GridSize {
  try {
    const raw = window.localStorage.getItem(GRID_STORAGE_KEY);
    if (raw === null) return DEFAULT_GRID;
    const n = Number(raw) as GridSize;
    return (GRID_OPTIONS as readonly number[]).includes(n) ? n : DEFAULT_GRID;
  } catch {
    return DEFAULT_GRID;
  }
}
