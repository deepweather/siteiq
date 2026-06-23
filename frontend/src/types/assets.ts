export interface AssetUpdate {
  id: string;
  type: 'worker' | 'equipment' | 'material' | 'facility';
  subtype: string;
  x: number;
  y: number;
  state: string;
  /** Multi-level: which level this asset is currently on. The backend
   *  always emits this (default "L0" for single-floor projects). */
  lvl?: string;
  /** Backend only includes this for assets that have a zone assignment
   *  (workers, equipment with an assigned zone). Absent on facilities. */
  assigned_zone?: string;
}

export interface Trail {
  [assetId: string]: [number, number][];
}
