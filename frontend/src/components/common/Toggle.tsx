interface ToggleProps {
  label: string;
  active: boolean;
  onChange: () => void;
}

export function Toggle({ label, active, onChange }: ToggleProps) {
  return (
    <button
      onClick={onChange}
      className={`px-3 py-1 text-xs font-medium rounded-md ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-card text-muted-foreground border border-border hover:bg-secondary'
      }`}
    >
      {label}
    </button>
  );
}
