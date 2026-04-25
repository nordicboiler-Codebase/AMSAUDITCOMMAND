import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Database, FileSearch, ListChecks, Package } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, MetricCard, PageHeader, SectionCard } from "@/components/ui/page";
import { api } from "@/lib/api";

interface PackRunDetail {
  id: string;
  pack_code: string;
  status: string;
  dataset_id: string;
  dataset_name: string;
  subledger_type?: string;
  started_at?: string;
  finished_at?: string;
  summary: Record<string, unknown>;
  ensemble_run_id?: string;
  test_runs: Array<{
    id: string;
    template_code?: string;
    detector_name: string;
    status: string;
    findings_count: number;
    started_at?: string;
    finished_at?: string;
  }>;
  template_overrides: Record<string, unknown>;
}

export function PackRunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: run } = useQuery({
    queryKey: ["pack-run", id],
    queryFn: () => api.get<PackRunDetail>(`/api/packs/runs/${id}`),
    enabled: !!id,
  });

  if (!run) return null;

  const completed = run.test_runs.filter((t) => t.status === "COMPLETED").length;
  const failed = run.test_runs.filter((t) => t.status === "FAILED").length;
  const totalFindings = run.test_runs.reduce((s, t) => s + (t.findings_count || 0), 0);
  const duration =
    run.started_at && run.finished_at
      ? `${Math.round((+new Date(run.finished_at) - +new Date(run.started_at)) / 1000)}s`
      : "—";

  return (
    <>
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>
      <PageHeader
        title={`Pack run · ${run.pack_code}`}
        description={`${run.dataset_name}${run.subledger_type ? ` · ${run.subledger_type.replace(/_/g, " ")}` : ""}`}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={run.status} />
            <Button
              variant="outline" size="sm"
              onClick={() => {
                localStorage.setItem("ts_active_dataset", run.dataset_id);
                navigate(`/datasets`);
              }}
            >
              <Database className="h-4 w-4" /> Open dataset
            </Button>
            {run.ensemble_run_id && (
              <Button
                variant="accent" size="sm"
                onClick={() => {
                  localStorage.setItem("ts_active_dataset", run.dataset_id);
                  navigate("/risk");
                }}
              >
                <FileSearch className="h-4 w-4" /> Open in Risk Explorer
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <MetricCard label="Templates run" value={run.test_runs.length} icon={<Package className="h-5 w-5" />} />
        <MetricCard label="Completed" value={completed} />
        <MetricCard label="Findings flagged" value={totalFindings}
                    accent={totalFindings > 0 ? "hsl(var(--accent))" : undefined} />
        <MetricCard label="Duration" value={duration} hint={failed ? `${failed} failed` : undefined} />
      </div>

      <SectionCard
        title="Templates in this pack"
        actions={
          <div className="text-xs text-muted-foreground">
            Click a row to drill into per-template flagged records.
          </div>
        }
      >
        {run.test_runs.length === 0 ? (
          <EmptyState
            icon={<ListChecks className="h-5 w-5" />}
            title="No template runs recorded"
            description="The pack may have errored before launching any templates."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Template</th>
                  <th className="text-left font-semibold py-2 px-3">Detector</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-right font-semibold py-2 px-3">Findings</th>
                  <th className="text-left font-semibold py-2 px-3">Finished</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {run.test_runs.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => navigate(`/runs/${t.id}`)}
                    className="cursor-pointer hover:bg-secondary/30"
                  >
                    <td className="py-2 px-3 font-mono text-xs font-medium text-accent">
                      {t.template_code || "—"}
                    </td>
                    <td className="py-2 px-3 font-mono text-xs text-muted-foreground">
                      {t.detector_name}
                    </td>
                    <td className="py-2 px-3"><StatusBadge status={t.status} /></td>
                    <td className="py-2 px-3 text-right tabular-nums font-medium">
                      {t.findings_count}
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">
                      {t.finished_at ? new Date(t.finished_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {Object.keys(run.template_overrides).length > 0 && (
        <SectionCard className="mt-4" title="Template overrides">
          <pre className="bg-secondary rounded-md p-3 text-[11px] overflow-auto max-h-[280px]">
            {JSON.stringify(run.template_overrides, null, 2)}
          </pre>
        </SectionCard>
      )}
    </>
  );
}
