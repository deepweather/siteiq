import { type ValidationIssue } from '../../services/projectsApi';

export function ValidationOverlay({ issues }: { issues: ValidationIssue[] }) {
  const errors = issues.filter((i) => i.severity === 'error');
  const warnings = issues.filter((i) => i.severity === 'warning');
  if (errors.length === 0 && warnings.length === 0) {
    return (
      <div className="border border-success/30 bg-success/5 rounded-lg p-2 text-xs">
        <span className="text-success font-semibold">All checks passing.</span>
      </div>
    );
  }
  return (
    <div className="border border-border rounded-lg overflow-hidden text-xs">
      <div className="px-2 py-1.5 bg-secondary text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Validation
      </div>
      <ul className="divide-y divide-border">
        {errors.map((i, idx) => (
          <li key={`e-${idx}`} className="px-2 py-1.5">
            <span className="font-semibold text-destructive">{i.code}</span>{' '}
            <span className="text-foreground">{i.message}</span>
          </li>
        ))}
        {warnings.map((i, idx) => (
          <li key={`w-${idx}`} className="px-2 py-1.5">
            <span className="font-semibold text-warning">{i.code}</span>{' '}
            <span className="text-muted-foreground">{i.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
