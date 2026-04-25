import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Package, Play } from "lucide-react";
import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface PackRunSummary {
  id: string;
  dataset_id: string;
  dataset_name: string;
  pack_code: string;
  status: string;
  started_at?: string;
  finished_at?: string;
  summary: { templates_run?: number };
}

interface Pack {
  code: string;
  name: string;
  description?: string;
  subledger_type?: string;
  template_codes: string[];
  is_system: boolean;
}

export function PacksPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [selected, setSelected] = useState<Pack | null>(null);
  const [datasetId, setDatasetId] = useState<string>("");
  const qc = useQueryClient();

  const { data: packs = [] } = useQuery({
    queryKey: ["packs"],
    queryFn: () => api.get<Pack[]>("/api/packs"),
  });
  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () => api.get<Array<{ id: string; name: string }>>(
      `/api/datasets${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
    enabled: !!activeProjectId,
  });
  const { data: packRuns = [] } = useQuery({
    queryKey: ["pack-runs", activeProjectId],
    queryFn: () => api.get<PackRunSummary[]>(
      `/api/packs/runs${activeProjectId ? `?project_id=${activeProjectId}&limit=20` : "?limit=20"}`,
    ),
  });

  const runMutation = useMutation({
    mutationFn: () => api.post<{ pack_run_id: string; summary: { templates_run: number } }>(
      "/api/packs/run",
      { dataset_id: datasetId, pack_code: selected!.code, template_overrides: {} },
    ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["all-runs"] });
      qc.invalidateQueries({ queryKey: ["pack-runs"] });
      toast({
        kind: "success",
        title: `Pack run complete — ${data.summary.templates_run} templates`,
      });
      navigate(`/packs/runs/${data.pack_run_id}`);
    },
    onError: (e) => toast({ kind: "error", title: "Pack run failed", description: (e as Error).message }),
  });

  return (
    <>
      <PageHeader
        title="Domain packs"
        description="Curated bundles of templates — run all tests for a subledger in one click."
      />
      {packs.length === 0 ? (
        <EmptyState
          icon={<Package className="h-5 w-5" />}
          title="No packs registered"
          description="Migrations seed 10 system packs on first run."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
            {packs.map((p) => (
              <div
                key={p.code}
                onClick={() => setSelected(p)}
                className={`rounded-lg border bg-card p-4 cursor-pointer transition-all hover:shadow-sm ${
                  selected?.code === p.code ? "ring-2 ring-accent border-accent" : ""
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                    {p.code}
                  </div>
                  {p.subledger_type && (
                    <Badge tone="muted">{p.subledger_type.replace(/_/g, " ")}</Badge>
                  )}
                </div>
                <div className="font-semibold text-sm mt-1">{p.name}</div>
                {p.description && (
                  <div className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {p.description}
                  </div>
                )}
                <div className="text-xs text-muted-foreground mt-3 font-medium">
                  {p.template_codes.length} templates
                </div>
              </div>
            ))}
          </div>

          <SectionCard title={selected ? selected.code : "Pack detail"}>
            {!selected ? (
              <div className="text-sm text-muted-foreground py-10 text-center">
                Select a pack to see templates + run it.
              </div>
            ) : (
              <>
                <div className="text-base font-semibold">{selected.name}</div>
                <div className="text-xs text-muted-foreground mt-1">{selected.description}</div>
                <div className="eyebrow mt-4 mb-2">Templates ({selected.template_codes.length})</div>
                <div className="max-h-[260px] overflow-auto text-xs font-mono grid grid-cols-3 gap-1">
                  {selected.template_codes.map((c) => (
                    <button
                      key={c}
                      onClick={(e) => { e.stopPropagation(); navigate(`/templates?code=${encodeURIComponent(c)}`); }}
                      className="px-2 py-1 bg-secondary rounded text-center hover:bg-accent/10 hover:text-accent transition-colors"
                      title="Open template"
                    >
                      {c}
                    </button>
                  ))}
                </div>
                <div className="eyebrow mt-6 mb-2">Run on dataset</div>
                <select
                  className="w-full h-9 px-3 rounded-md border border-input bg-card text-sm mb-3"
                  value={datasetId}
                  onChange={(e) => setDatasetId(e.target.value)}
                >
                  <option value="">Pick a dataset…</option>
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
                <Button
                  className="w-full"
                  onClick={() => runMutation.mutate()}
                  disabled={!datasetId || runMutation.isPending}
                >
                  <Play className="h-4 w-4" />
                  {runMutation.isPending ? "Running…" : `Run ${selected.code}`}
                </Button>
              </>
            )}
          </SectionCard>
        </div>
      )}

      {packRuns.length > 0 && (
        <SectionCard
          className="mt-6"
          title={`Recent pack runs (${packRuns.length})`}
          actions={<History className="h-4 w-4 text-muted-foreground" />}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Pack</th>
                  <th className="text-left font-semibold py-2 px-3">Dataset</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-right font-semibold py-2 px-3">Templates</th>
                  <th className="text-left font-semibold py-2 px-3">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {packRuns.map((pr) => (
                  <tr
                    key={pr.id}
                    onClick={() => navigate(`/packs/runs/${pr.id}`)}
                    className="cursor-pointer hover:bg-secondary/30"
                  >
                    <td className="py-2 px-3 font-mono text-xs font-medium text-accent">
                      {pr.pack_code}
                    </td>
                    <td className="py-2 px-3 text-sm">{pr.dataset_name}</td>
                    <td className="py-2 px-3"><StatusBadge status={pr.status} /></td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {pr.summary.templates_run ?? "—"}
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">
                      {pr.started_at ? new Date(pr.started_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </>
  );
}
