import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";

export interface AiProviderStatus {
  provider: string;
  label: string;
  enabled: boolean;
  configured: boolean;
  sdk_installed: boolean;
  model: string;
}

export interface AiStatus {
  enabled: boolean;
  model: string | null;
  reason: string;
  active: string | null;
  providers: AiProviderStatus[];
}

export function useAiStatus() {
  return useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api.get<AiStatus>("/api/ai/status"),
    staleTime: 60_000,
  });
}

export function AiStatusBadge({ className = "" }: { className?: string }) {
  const { data } = useAiStatus();
  if (!data) return null;
  if (data.enabled) {
    const activeLabel = data.providers?.find((p) => p.provider === data.active)?.label ?? data.active;
    return (
      <span
        title={`${activeLabel} ready — model ${data.model}`}
        className={`inline-flex items-center gap-1 rounded-full bg-success/10 text-success border border-success/30 px-2 py-0.5 text-[11px] font-medium ${className}`}
      >
        <Sparkles className="h-3 w-3" /> AI on
        <span className="font-mono opacity-70 ml-0.5">{data.model}</span>
      </span>
    );
  }
  return (
    <span
      title={data.reason}
      className={`inline-flex items-center gap-1 rounded-full bg-muted text-muted-foreground border px-2 py-0.5 text-[11px] font-medium ${className}`}
    >
      <Sparkles className="h-3 w-3" /> AI off
    </span>
  );
}

export function AiOffBanner() {
  const { data } = useAiStatus();
  if (!data || data.enabled) return null;
  return (
    <div className="rounded-md border border-warning/40 bg-warning/5 p-3 mb-4 text-xs flex items-start gap-2">
      <Sparkles className="h-4 w-4 text-warning shrink-0 mt-0.5" />
      <div>
        <span className="font-semibold">AI features disabled</span> — {data.reason}.{" "}
        <span className="text-muted-foreground">
          Configure providers under <span className="font-medium text-foreground">Settings → AI Providers</span>.
        </span>
      </div>
    </div>
  );
}
