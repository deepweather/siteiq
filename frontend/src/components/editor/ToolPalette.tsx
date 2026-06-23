/** Tool palette for the project editor — placing new assets. */

export type EditorTool =
  | 'select'
  | 'add-zone'
  | 'add-toilet'
  | 'add-breakroom'
  | 'add-office'
  | 'add-toolcrib'
  | 'add-stair'
  | 'add-elevator'
  | 'add-crane'
  | 'add-pump'
  | 'add-excavator'
  | 'add-sheet-pile'
  | 'add-dewatering-pump';

interface ToolButton {
  tool: EditorTool;
  label: string;
  category: 'edit' | 'zone' | 'facility' | 'vertical' | 'equipment' | 'tiefbau';
}

const BUTTONS: ToolButton[] = [
  { tool: 'select', label: 'Select / Move', category: 'edit' },
  { tool: 'add-zone', label: 'Zone', category: 'zone' },
  { tool: 'add-toilet', label: 'Toilet', category: 'facility' },
  { tool: 'add-breakroom', label: 'Breakroom', category: 'facility' },
  { tool: 'add-office', label: 'Office', category: 'facility' },
  { tool: 'add-toolcrib', label: 'Toolcrib', category: 'facility' },
  { tool: 'add-stair', label: 'Stair', category: 'vertical' },
  { tool: 'add-elevator', label: 'Elevator', category: 'vertical' },
  { tool: 'add-crane', label: 'Crane', category: 'equipment' },
  { tool: 'add-pump', label: 'Concrete pump', category: 'equipment' },
  { tool: 'add-excavator', label: 'Excavator', category: 'equipment' },
  { tool: 'add-sheet-pile', label: 'Sheet pile', category: 'tiefbau' },
  { tool: 'add-dewatering-pump', label: 'Dewatering pump', category: 'tiefbau' },
];

const CATEGORY_LABEL: Record<ToolButton['category'], string> = {
  edit: 'Edit',
  zone: 'Zones',
  facility: 'Facilities',
  vertical: 'Vertical transport',
  equipment: 'Equipment',
  tiefbau: 'Tiefbau',
};

interface ToolPaletteProps {
  tool: EditorTool;
  onChange: (tool: EditorTool) => void;
}

export function ToolPalette({ tool, onChange }: ToolPaletteProps) {
  const categories = ['edit', 'zone', 'facility', 'vertical', 'equipment', 'tiefbau'] as const;
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-2 py-1.5 bg-secondary text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Tools
      </div>
      <div className="p-2 space-y-2.5">
        {categories.map((cat) => {
          const inCat = BUTTONS.filter((b) => b.category === cat);
          if (!inCat.length) return null;
          return (
            <div key={cat}>
              <div className="text-[10px] text-muted-foreground/70 mb-1">{CATEGORY_LABEL[cat]}</div>
              <div className="grid grid-cols-2 gap-1">
                {inCat.map((b) => (
                  <button
                    key={b.tool}
                    type="button"
                    onClick={() => onChange(b.tool)}
                    className={
                      'text-xs px-2 py-1 rounded border text-left ' +
                      (tool === b.tool
                        ? 'border-primary bg-primary/10 text-foreground'
                        : 'border-border hover:bg-secondary')
                    }
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
