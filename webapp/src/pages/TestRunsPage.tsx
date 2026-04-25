import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { StatusBadge } from "@/components/ui/badge";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api, type TestRun } from "@/lib/api";

export function TestRunsPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const navigate = useNavigate();

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () => api.get<Array<{ id: string; name: string }>>(
      `/api/datasets${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
  });

  // Fan out — one runs query per dataset, flatten
  const { data: runs = [] } = useQuery({
    queryKey: ["all-runs", datasets.map((d) => d.id)],
    queryFn: async () => {
      const all = await Promise.all(
        datasets.map((d) =>
          api.get<TestRun[]>(`/api/datasets/${d.id}/runs`).then((rs) =>
            rs.map((r) => ({ ...r, dataset_name: d.name })),
          ),
        ),
      );
      return all.flat().sort((a, b) =>
        (b.started_at || "").localeCompare(a.started_at || ""),
      );
    },
    enabled: datasets.length > 0,
  });

  return (
    <>
      <PageHeader
        title="Test runs"
        description="Every test execution. Input and output hashes captured for audit integrity."
      />
      {runs.length === 0 ? (
        <EmptyState
          icon={<History className="h-5 w-5" />}
          title="No runs yet"
          description="Execute a template or pack from the Run page to see history here."
        />
      ) : (
        <SectionCard title={`${runs.length} runs`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Started</th>
                  <th className="text-left font-semibold py-2 px-3">Template / Detector</th>
                  <th className="text-left font-semibold py-2 px-3">Dataset</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-right font-semibold py-2 px-3">Findings</th>
                  <th className="text-left font-semibold py-2 px-3">Input hash</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {runs.slice(0, 300).map((r) => (
                  <tr
                    key={r.id}
                    className="hover:bg-secondary/30 cursor-pointer"
                    onClick={() => navigate(`/runs/${r.id}`)}
                  >
                    <td className="py-2 px-3 text-xs font-mono">
                      {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                    </td>
                    <td className="py-2 px-3">
                      <span className="font-mono text-xs font-semibold">
                        {r.template_code || "—"}
                      </span>
                      <span className="text-xs text-muted-foreground ml-2">
                        {r.detector_name}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-muted-foreground">
                      {(r as TestRun & { dataset_name?: string }).dataset_name}
                    </td>
                    <td className="py-2 px-3"><StatusBadge status={r.status} /></td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {r.findings_count || 0}
                    </td>
                    <td className="py-2 px-3 font-mono text-[10px] text-muted-foreground">
                      {(r as TestRun & { input_hash?: string }).input_hash?.slice(0, 10) || "—"}…
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
