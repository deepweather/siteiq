export interface AssetUpdate {
  id: string;
  type: 'worker' | 'equipment' | 'material' | 'facility';
  subtype: string;
  x: number;
  y: number;
  state: string;
}

export interface Trail {
  [assetId: string]: [number, number][];
}
