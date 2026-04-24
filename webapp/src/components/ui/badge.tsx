import { cn } from "@/lib/utils";

type Tone = "default" | "muted" | "success" | "warning" | "danger" | "info" | "accent";

const tones: Record<Tone, string> = {
  default: "bg-muted text-muted-foreground",
  muted: "bg-muted text-muted-foreground",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-destructive/15 text-destructive",
  info: "bg-blue-500/15 text-blue-700",
  accent: "bg-accent/15 text-accent-foreground",
};

export function Badge({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const severityTone: Record<string, Tone> = {
  CRITICAL: "danger",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "info",
};
export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={severityTone[severity] || "muted"}>{severity}</Badge>;
}

const statusTone: Record<string, Tone> = {
  DRAFT: "muted",
  UNDER_REVIEW: "info",
  CONFIRMED: "danger",
  FALSE_POSITIVE: "muted",
  REMEDIATED: "success",
  ACCEPTED_RISK: "warning",
  CARRIED_FORWARD: "info",
  ACTIVE: "success",
  PAUSED: "muted",
  PLANNING: "muted",
  IN_PROGRESS: "info",
  REVIEW: "warning",
  FINALISED: "success",
  ARCHIVED: "muted",
  COMPLETED: "success",
  RUNNING: "info",
  PENDING: "muted",
  FAILED: "danger",
};
export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone[status] || "muted"}>{status.replace(/_/g, " ")}</Badge>;
}
