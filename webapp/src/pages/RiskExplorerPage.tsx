import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Target } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api, type RiskScore, type TestRun } from "@/lib/api";

function sev(score: number) {
  if (score >= 90) return "CRITICAL";
  if (score >= 70) return "HIGH";
  if (score >= 40) return "MEDIUM";
  return "LOW";
}

export function RiskExplorerPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const [datasetId, setDatasetId] = useState<string | null>(
    () => localStorage.getItem("ts_active_dataset"),
  );
  const [minScore, setMinScore] = useState(50);
  const [selected, setSelected] = useState<RiskScore | null>(null);

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () => api.get<Array<{ id: string; name: string; record_count: number }>>(
      `/api/datasets${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
  });

  const { data: scores = [], refetch: refetchScores } = useQuery({
    queryKey: ["risk", datasetId, minScore],
    queryFn: () => api.get<RiskScore[]>(
      `/api/datasets/${datasetId}/risk-scores?min_score=${minScore}&limit=500&sort=desc`,
    ),
    enabled: !!datasetId,
  });

  async function runEnsemble() {
    if (!datasetId) return;
    const runs = await api.get<TestRun[]>(`/api/datasets/${datasetId}/runs`);
    const completed = runs.filter((r) => r.status === "COMPLETED").map((r) => r.id);
    if (!completed.length) return alert("No completed test runs on this dataset yet.");
    await api.post("/api/ensemble", { dataset_id: datasetId, test_run_ids: completed });
    refetchScores();
  }

  return (
    <>
      <PageHeader
        title="Risk Explorer"
        description="Every record scored 0–100 with per-detector explainability. Click a row to drill down."
        actions={
          datasetId ? (
            <Button onClick={runEnsemble} variant="accent">
              <RefreshCw className="h-4 w-4" /> Recompute ensemble
            </Button>
          ) : null
        }
      />

      <div className="rounded-lg border bg-card p-4 mb-4 flex items-center gap-4 flex-wrap">
        <div className="flex-1 min-w-[260px]">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Dataset
          </div>
          <select
            className="w-full h-9 px-3 rounded-md border border-input bg-card text-sm"
            value={datasetId ?? ""}
            onChange={(e) => {
              const v = e.target.value || null;
              setDatasetId(v);
              if (v) localStorage.setItem("ts_active_dataset", v);
              else localStorage.removeItem("ts_active_dataset");
            }}
          >
            <option value="">Pick a dataset…</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.record_count.toLocaleString()} rows)
              </option>
            ))}
          </select>
        </div>
        <div className="w-[280px]">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Min score: {minScore}
          </div>
          <input
            type="range" min={0} max={100} value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="w-full accent-accent"
          />
        </div>
      </div>

      {!datasetId ? (
        <EmptyState
          icon={<Target className="h-5 w-5" />}
          title="No dataset selected"
          description="Pick a dataset above to explore its risk scores."
        />
      ) : scores.length === 0 ? (
        <EmptyState
          icon={<Target className="h-5 w-5" />}
          title="No scores in this range"
          description="Lower the minimum score, or recompute the ensemble."
          action={<Button onClick={runEnsemble} variant="accent">Recompute ensemble</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SectionCard className="lg:col-span-2" title={`${scores.length} records`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left font-semibold py-2 px-3">Record key</th>
                    <th className="text-right font-semibold py-2 px-3">Score</th>
                    <th className="text-left font-semibold py-2 px-3">Severity</th>
                    <th className="text-right font-semibold py-2 px-3">Detectors</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {scores.map((r) => (
                    <tr
                      key={r.record_key}
                      onClick={() => setSelected(r)}
                      className={`cursor-pointer hover:bg-secondary/30 ${
                        selected?.record_key === r.record_key ? "bg-secondary/40" : ""
                      }`}
                    >
                      <td className="py-2 px-3 font-mono text-xs truncate max-w-[200px]">{r.record_key}</td>
                      <td className="py-2 px-3 text-right font-semibold tabular-nums">
                        {r.score.toFixed(1)}
                      </td>
                      <td className="py-2 px-3"><SeverityBadge severity={sev(r.score)} /></td>
                      <td className="py-2 px-3 text-right text-muted-foreground tabular-nums">
                        {r.contributing_detectors.length}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard title={selected ? `Record ${selected.record_key}` : "Detail"}>
            {!selected ? (
              <div className="text-sm text-muted-foreground py-10 text-center">
                Select a row to see detector explainability.
              </div>
            ) : (
              <>
                <div className="mb-4 text-3xl font-bold tabular-nums">
                  {selected.score.toFixed(1)}
                  <span className="ml-2 text-sm">
                    <SeverityBadge severity={sev(selected.score)} />
                  </span>
                </div>
                <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2">
                  Why this record scored
                </div>
                <div className="space-y-2">
                  {selected.contributing_detectors.map((c, i) => (
                    <div key={i} className="text-sm border-l-2 border-accent pl-3 py-1">
                      <div className="font-medium">{c.detector_name}</div>
                      <div className="text-xs text-muted-foreground">
                        template {c.template_code || "n/a"} · weight {c.weight?.toFixed(1) ?? "—"}
                      </div>
                      {c.reason && <div className="text-xs mt-1">{c.reason}</div>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </SectionCard>
        </div>
      )}
    </>
  );
}
