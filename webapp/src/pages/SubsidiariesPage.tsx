import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus } from "lucide-react";
import { useState } from "react";
import { SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, type Subsidiary, type SubsidiaryRollup } from "@/lib/api";
import { useToast } from "@/lib/toast";

export function SubsidiariesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

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
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> Register subsidiary
          </Button>
        }
      />
      {subs.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-5 w-5" />}
          title="No subsidiaries yet"
          description="Register the group entities you audit — one row per subsidiary / entity."
          action={<Button onClick={() => setOpen(true)}>Register first subsidiary</Button>}
        />
      ) : (
        <SectionCard title={`${subs.length} entities · ${rollup.reduce((s, r) => s + r.findings_open, 0)} open findings group-wide`}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {subs.map((s) => {
              const r = rollupMap[s.code];
              return (
                <div key={s.id} className="rounded-lg border bg-card p-4 hover:shadow-md transition-shadow">
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
                        <div
                          className="font-semibold tabular-nums"
                          style={{
                            color:
                              r.max_risk_score >= 90 ? "hsl(var(--destructive))" :
                              r.max_risk_score >= 70 ? "hsl(var(--destructive))" :
                              r.max_risk_score >= 40 ? "hsl(var(--warning))" : undefined,
                          }}
                        >
                          {r.max_risk_score.toFixed(0)}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      {open && (
        <CreateSubsidiaryDialog
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["subsidiaries"] });
            qc.invalidateQueries({ queryKey: ["rollup"] });
          }}
        />
      )}
    </>
  );
}

function CreateSubsidiaryDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [country, setCountry] = useState("");
  const [industry, setIndustry] = useState("");
  const [segment, setSegment] = useState("");
  const [riskRating, setRiskRating] = useState("MEDIUM");

  const mutation = useMutation({
    mutationFn: () => api.post("/api/subsidiaries", {
      code, name,
      country: country || null, industry: industry || null,
      segment: segment || null, risk_rating: riskRating,
      is_active: true,
    }),
    onSuccess: () => {
      toast({ kind: "success", title: "Subsidiary registered", description: code });
      onCreated();
    },
    onError: (e) => {
      toast({ kind: "error", title: "Failed", description: (e as Error).message });
    },
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b">
          <h3 className="text-base font-semibold">Register subsidiary</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            One row per group entity. Code is uppercase and must be unique.
          </p>
        </div>
        <div className="p-5 grid grid-cols-2 gap-3">
          <div>
            <Label>Code *</Label>
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="DI-001"
              autoFocus
            />
          </div>
          <div>
            <Label>Risk rating</Label>
            <Select value={riskRating} onChange={(e) => setRiskRating(e.target.value)}>
              <option value="LOW">LOW</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="HIGH">HIGH</option>
              <option value="CRITICAL">CRITICAL</option>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Name *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)}
                   placeholder="Dubai Investments PJSC" />
          </div>
          <div>
            <Label>Country (3-letter)</Label>
            <Input value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())}
                   placeholder="ARE" maxLength={4} />
          </div>
          <div>
            <Label>Industry</Label>
            <Input value={industry} onChange={(e) => setIndustry(e.target.value)}
                   placeholder="Holdings" />
          </div>
          <div className="col-span-2">
            <Label>Business segment</Label>
            <Input value={segment} onChange={(e) => setSegment(e.target.value)}
                   placeholder="Diversified holdings" />
          </div>
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!code || !name || mutation.isPending}>
            {mutation.isPending ? "Registering…" : "Register"}
          </Button>
        </div>
      </div>
    </div>
  );
}
