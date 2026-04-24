import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { SeverityBadge } from "@/components/ui/badge";
import { EmptyState, PageHeader } from "@/components/ui/page";
import { api, type Subsidiary, type SubsidiaryRollup } from "@/lib/api";

export function SubsidiariesPage() {
  const { data: subs = [] } = useQuery({
    queryKey: ["subsidiaries"],
    queryFn: () => api.get<Subsidiary[]>("/api/subsidiaries"),
  });
  const { data: rollup = [] } = useQuery({
    queryKey: ["rollup"],
    queryFn: () => api.get<SubsidiaryRollup[]>("/api/subsidiaries/rollup"),
  });
  const rollupMap = Object.fromEntries(rollup.map((r) => [r.code, r]));

  return (
    <>
      <PageHeader
        title="Subsidiaries"
        description="Group entities under audit scope. Risk rating + live rollup shown per entity."
      />
      {subs.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-5 w-5" />}
          title="No subsidiaries yet"
          description="Register the group entities you audit — one row per subsidiary / entity."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {subs.map((s) => {
            const r = rollupMap[s.code];
            return (
              <div key={s.id} className="rounded-lg border bg-card p-4 hover:shadow-sm transition-shadow">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
                      {s.code}
                    </div>
                    <div className="font-semibold text-sm mt-0.5 truncate">{s.name}</div>
                  </div>
                  {s.risk_rating ? <SeverityBadge severity={s.risk_rating} /> : null}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {[s.country, s.segment].filter(Boolean).join(" · ") || "—"}
                </div>
                {r && (
                  <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
                    <div>
                      <div className="text-muted-foreground">Open</div>
                      <div className="font-semibold tabular-nums">{r.findings_open}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">H/C</div>
                      <div className="font-semibold tabular-nums">{r.findings_high_critical}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Max risk</div>
                      <div className="font-semibold tabular-nums">{r.max_risk_score.toFixed(0)}</div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
