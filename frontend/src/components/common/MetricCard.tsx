import { formatCurrency } from '../../utils/formatting';

interface MetricCardProps {
  title: string;
  dailyCost: number;
  monthlyCost: number;
  detail: string;
  children?: React.ReactNode;
}

export function MetricCard({ title, dailyCost, monthlyCost, detail, children }: MetricCardProps) {
  return (
    <div className="py-2">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="flex items-baseline gap-2 mt-0.5">
        <span className="font-mono text-lg font-semibold text-destructive tabular-nums">
          {formatCurrency(dailyCost)}
          <span className="text-xs text-muted-foreground font-normal ml-0.5">/d</span>
        </span>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">
          {formatCurrency(monthlyCost)}/mo
        </span>
      </div>
      <div className="text-xs text-muted-foreground mt-0.5">{detail}</div>
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
}
