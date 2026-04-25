import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, FileSearch, ListChecks,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, MetricCard, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, type TestRun } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface FlaggedResponse {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  total: number;
  limit: number;
  offset: number;
  summary: Record<string, unknown> | null;
}

export function TestRunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: run } = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.get<TestRun & { dataset_id: string }>(`/api/runs/${id}`),
    enabled: !!id,
  });

  const { data: flagged } = useQuery({
    queryKey: ["run-flagged", id],
    queryFn: () => api.get<FlaggedResponse>(`/api/runs/${id}/flagged?limit=500`),
    enabled: !!id,
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchOpen, setBatchOpen] = useState(false);

  if (!run) return null;

  const allSelected =
    !!flagged?.rows.length && flagged.rows.every((r) => selected.has(String(r._record_key)));

  return (
    <>
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>
      <PageHeader
        title={run.template_code || run.detector_name}
        description={`Test run · ${run.detector_name}`}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={run.status || "PENDING"} />
            {run.findings_count > 0 && (
              <Button
                variant="accent"
                onClick={() => setBatchOpen(true)}
                disabled={selected.size === 0}
              >
                <FileSearch className="h-4 w-4" />
                Create finding ({selected.size || "select rows"})
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard
          label="Flagged records" value={run.findings_count || 0}
          icon={<AlertTriangle className="h-5 w-5" />}
          accent={run.findings_count > 0 ? "hsl(0 70% 50%)" : undefined}
        />
        <MetricCard label="Status" value={run.status || "—"} />
        <MetricCard
          label="Duration"
          value={
            run.started_at && run.finished_at
              ? `${Math.round((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 100) / 10}s`
              : "—"
          }
        />
        <MetricCard
          label="Run at"
          value={run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <SectionCard
          className="lg:col-span-2"
          title={`Flagged records (${flagged?.total ?? 0})`}
          actions={
            flagged && flagged.rows.length > 0 ? (
              <Button
                variant="outline" size="sm"
                onClick={() => {
                  if (allSelected) {
                    setSelected(new Set());
                  } else {
                    setSelected(new Set(flagged.rows.map((r) => String(r._record_key))));
                  }
                }}
              >
                <ListChecks className="h-3.5 w-3.5" />
                {allSelected ? "Clear" : "Select all"}
              </Button>
            ) : null
          }
        >
          {!flagged || flagged.rows.length === 0 ? (
            <EmptyState
              icon={<FileSearch className="h-5 w-5" />}
              title="No flagged records"
              description={run.status === "FAILED"
                ? `Run failed: ${run.error_message || "unknown error"}`
                : "This run produced 0 findings — no records met the detector's criteria."}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground sticky top-0 bg-card">
                  <tr>
                    <th className="text-left font-semibold py-2 px-2 w-8"></th>
                    <th className="text-left font-semibold py-2 px-3">Record</th>
                    <th className="text-left font-semibold py-2 px-3">Reason</th>
                    {flagged.columns
                      .filter((c) => !c.startsWith("_") && !["record_id"].includes(c))
                      .slice(0, 5)
                      .map((c) => (
                        <th key={c} className="text-left font-semibold py-2 px-3">{c}</th>
                      ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {flagged.rows.map((r) => {
                    const key = String(r._record_key);
                    const selectedNow = selected.has(key);
                    return (
                      <tr
                        key={key}
                        className={`hover:bg-secondary/30 cursor-pointer ${
                          selectedNow ? "bg-accent/10" : ""
                        }`}
                        onClick={() => {
                          const next = new Set(selected);
                          if (next.has(key)) next.delete(key);
                          else next.add(key);
                          setSelected(next);
                        }}
                      >
                        <td className="py-2 px-2">
                          <input
                            type="checkbox" readOnly checked={selectedNow}
                            className="accent-accent"
                          />
                        </td>
                        <td className="py-2 px-3 font-mono text-xs">{key}</td>
                        <td className="py-2 px-3 text-xs text-muted-foreground max-w-[280px] truncate">
                          {String(r._reason ?? "")}
                        </td>
                        {flagged.columns
                          .filter((c) => !c.startsWith("_") && !["record_id"].includes(c))
                          .slice(0, 5)
                          .map((c) => (
                            <td key={c} className="py-2 px-3 text-xs truncate max-w-[160px]">
                              {String(r[c] ?? "")}
                            </td>
                          ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {flagged.total > flagged.rows.length && (
                <div className="text-xs text-muted-foreground mt-2 text-center">
                  Showing {flagged.rows.length} of {flagged.total} — paginate to see more
                </div>
              )}
            </div>
          )}
        </SectionCard>

        <div className="space-y-4">
          <SectionCard title="Run metadata">
            <dl className="space-y-2 text-xs">
              <Row label="Template" value={run.template_code ?? "—"} mono />
              <Row label="Detector" value={run.detector_name} mono />
              <Row label="Run ID" value={(run.id || "").slice(0, 8) + "…"} mono />
              <Row label="Dataset"
                   value={
                     <Link to="/datasets" className="text-accent hover:underline">
                       open ↗
                     </Link>
                   } />
              <Row label="Input hash" value={(run.input_hash || "").slice(0, 12) + "…"} mono />
              <Row label="Output hash" value={(run.output_hash || "").slice(0, 12) + "…"} mono />
            </dl>
          </SectionCard>

          <SectionCard title="Detector parameters">
            <pre className="bg-secondary rounded-md p-3 text-[11px] overflow-auto max-h-[200px]">
              {JSON.stringify(run.params, null, 2)}
            </pre>
          </SectionCard>

          {run.summary && (
            <SectionCard title="Summary">
              <pre className="bg-secondary rounded-md p-3 text-[11px] overflow-auto max-h-[300px]">
                {JSON.stringify(run.summary, null, 2)}
              </pre>
            </SectionCard>
          )}
        </div>
      </div>

      {batchOpen && id && (
        <BatchCreateFindingDialog
          runId={id}
          run={run}
          recordKeys={Array.from(selected)}
          onClose={() => setBatchOpen(false)}
        />
      )}
    </>
  );
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono" : ""}>{value}</dd>
    </div>
  );
}

function BatchCreateFindingDialog({
  runId, run, recordKeys, onClose,
}: {
  runId: string;
  run: TestRun & { dataset_id: string };
  recordKeys: string[];
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const projectIdFromStorage = localStorage.getItem("ts_active_project");

  const defaultSeverity = recordKeys.length >= 10 ? "HIGH" : recordKeys.length >= 3 ? "MEDIUM" : "LOW";
  const detectorTitle = run.template_code ? `${run.template_code} · ${run.detector_name}` : run.detector_name;
  const [title, setTitle] = useState(
    `${recordKeys.length} record${recordKeys.length === 1 ? "" : "s"} flagged by ${detectorTitle}`,
  );
  const [description, setDescription] = useState(
    `Auto-aggregated finding from test run ${runId.slice(0, 8)}.\n\n` +
    `Detector: ${run.detector_name}\n` +
    `Template: ${run.template_code || "n/a"}\n` +
    `Records flagged: ${recordKeys.length}`,
  );
  const [severity, setSeverity] = useState(defaultSeverity);
  const [project, setProject] = useState(projectIdFromStorage || "");

  const mutation = useMutation({
    mutationFn: () => api.post<{ id: string; code: string }>("/api/findings", {
      project_id: project,
      title,
      description,
      severity,
      dataset_id: run.dataset_id,
      record_keys: recordKeys,
      linked_template_codes: run.template_code ? [run.template_code] : [],
      tags: ["from-test-run"],
    }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["findings"] });
      toast({
        kind: "success",
        title: `Finding ${created.code} created`,
        description: `${recordKeys.length} record${recordKeys.length === 1 ? "" : "s"} linked.`,
      });
      onClose();
      navigate(`/findings/${created.id}`);
    },
    onError: (e) => toast({
      kind: "error", title: "Could not create finding",
      description: (e as Error).message,
    }),
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b">
          <h3 className="text-base font-semibold">Create finding from {recordKeys.length} record{recordKeys.length === 1 ? "" : "s"}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            One DRAFT finding linking all selected records. A reviewer (≠ you) confirms or closes.
          </p>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <Label>Project</Label>
            <Input
              value={project} onChange={(e) => setProject(e.target.value)}
              placeholder="Project UUID — defaults to active project"
            />
          </div>
          <div>
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <Label>Severity</Label>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              value={description} onChange={(e) => setDescription(e.target.value)}
              rows={5}
            />
          </div>
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!project || !title || mutation.isPending}
          >
            {mutation.isPending ? "Creating…" : "Create finding"}
          </Button>
        </div>
      </div>
    </div>
  );
}
