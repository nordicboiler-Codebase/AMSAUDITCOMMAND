import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-6 pb-6 mb-6 border-b", className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-card p-10 text-center">
      <div className="mx-auto h-12 w-12 flex items-center justify-center rounded-full bg-muted text-muted-foreground mb-4">
        {icon}
      </div>
      <div className="text-base font-semibold">{title}</div>
      <div className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">{description}</div>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  trend,
  icon,
  accent,
}: {
  label: string;
  value: string | number;
  hint?: string;
  trend?: "up" | "down" | "flat";
  icon?: React.ReactNode;
  accent?: string;
}) {
  const trendColor = trend === "up" ? "text-destructive" : trend === "down" ? "text-success" : "text-muted-foreground";
  return (
    <div
      className="relative rounded-lg border bg-card p-5 transition-all hover:shadow-sm hover:-translate-y-px"
      style={accent ? { borderLeft: `3px solid ${accent}` } : undefined}
    >
      {icon && <div className="absolute top-4 right-4 text-muted-foreground/60">{icon}</div>}
      <div className="metric-label">{label}</div>
      <div className="metric-value mt-2">{value}</div>
      {hint && <div className={cn("text-xs mt-2 font-medium", trendColor)}>{hint}</div>}
    </div>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border bg-card p-5", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            {title && <div className="eyebrow">{title}</div>}
            {description && <div className="text-sm text-muted-foreground mt-1">{description}</div>}
          </div>
          {actions && <div>{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
