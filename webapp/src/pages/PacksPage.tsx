import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Package, Play } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api } from "@/lib/api";

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

  const runMutation = useMutation({
    mutationFn: () => api.post("/api/packs/run", {
      dataset_id: datasetId,
      pack_code: selected!.code,
      template_overrides: {},
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
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
                    <div key={c} className="px-2 py-1 bg-secondary rounded text-center">{c}</div>
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
                {runMutation.isSuccess && runMutation.data ? (
                  <div className="mt-3 text-xs text-success">
                    Pack complete — {(runMutation.data as { summary: { templates_run: number } }).summary.templates_run} templates ran.
                  </div>
                ) : null}
                {runMutation.isError && (
                  <div className="mt-3 text-xs text-destructive">
                    {(runMutation.error as Error).message}
                  </div>
                )}
              </>
            )}
          </SectionCard>
        </div>
      )}
    </>
  );
}
