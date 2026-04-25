import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Clock, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

interface ScheduleRunRow {
  id: string;
  started_at?: string;
  finished_at?: string;
  status: string;
  summary: {
    pack_run_id?: string;
    test_run_id?: string;
    ensemble_run_id?: string;
    templates_run?: number;
    findings?: number;
    max_score?: number;
    records_scored?: number;
    error?: string;
  };
  alert_sent: boolean;
  alert_error?: string;
}

interface Schedule {
  id: string;
  name: string;
  project_id: string;
  dataset_id?: string;
  kind: "PACK" | "TEMPLATE";
  pack_code?: string;
  template_code?: string;
  cron_expr: string;
  status: string;
  alert_enabled: boolean;
  alert_min_score: number;
  alert_recipients: string[];
  next_run_at?: string;
  last_run_at?: string;
  last_run_status?: string;
}

export function SchedulesPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: schedules = [] } = useQuery({
    queryKey: ["schedules", activeProjectId],
    queryFn: () => api.get<Schedule[]>(
      `/api/schedules${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
    enabled: !!activeProjectId,
  });

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Schedules" description="Cron-driven runs with alerts." />
        <EmptyState
          icon={<Clock className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the sidebar first."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Schedules"
        description="Cron-driven pack / template runs with email alerts when risk crosses a threshold."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New schedule</Button>}
      />

      {schedules.length === 0 ? (
        <EmptyState
          icon={<Clock className="h-5 w-5" />}
          title="No schedules configured"
          description="Create one to run the monthly AP pack automatically with email alerts."
          action={<Button onClick={() => setOpen(true)}>Create schedule</Button>}
        />
      ) : (
        <SectionCard title={`${schedules.length} schedules`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Name</th>
                  <th className="text-left font-semibold py-2 px-3">Target</th>
                  <th className="text-left font-semibold py-2 px-3">Cron</th>
                  <th className="text-left font-semibold py-2 px-3">Next run</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-left font-semibold py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {schedules.map((s) => <ScheduleRow key={s.id} schedule={s} onChange={() =>
                  qc.invalidateQueries({ queryKey: ["schedules"] })
                } />)}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {open && (
        <CreateScheduleDialog
          projectId={activeProjectId}
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["schedules"] });
          }}
        />
      )}
    </>
  );
}

function ScheduleRow({ schedule, onChange }: { schedule: Schedule; onChange: () => void }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const runNow = useMutation({
    mutationFn: () => api.post(`/api/schedules/${schedule.id}/run-now`),
    onSuccess: onChange,
  });
  const toggle = useMutation({
    mutationFn: () => api.patch(`/api/schedules/${schedule.id}`, {
      status: schedule.status === "ACTIVE" ? "PAUSED" : "ACTIVE",
    }),
    onSuccess: onChange,
  });
  const del = useMutation({
    mutationFn: () => api.delete(`/api/schedules/${schedule.id}`),
    onSuccess: onChange,
  });
  const { data: history = [] } = useQuery({
    queryKey: ["schedule-runs", schedule.id],
    queryFn: () => api.get<ScheduleRunRow[]>(`/api/schedules/${schedule.id}/runs`),
    enabled: expanded,
  });

  function targetForRun(s: ScheduleRunRow["summary"]): string | null {
    if (s.pack_run_id) return `/packs/runs/${s.pack_run_id}`;
    if (s.test_run_id) return `/runs/${s.test_run_id}`;
    return null;
  }

  return (
    <>
      <tr className="hover:bg-secondary/30">
        <td className="py-2 px-3 font-medium">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 hover:text-accent"
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            {schedule.name}
          </button>
        </td>
        <td className="py-2 px-3 font-mono text-xs">
          {schedule.kind === "PACK" ? (
            <button
              onClick={() => navigate(`/packs`)}
              className="hover:text-accent"
              title="Open pack"
            >
              {schedule.kind}: {schedule.pack_code}
            </button>
          ) : (
            <button
              onClick={() => navigate(`/templates?code=${encodeURIComponent(schedule.template_code || "")}`)}
              className="hover:text-accent"
              title="Open template"
            >
              {schedule.kind}: {schedule.template_code}
            </button>
          )}
        </td>
        <td className="py-2 px-3 font-mono text-xs">{schedule.cron_expr}</td>
        <td className="py-2 px-3 text-xs text-muted-foreground">
          {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "—"}
        </td>
        <td className="py-2 px-3"><StatusBadge status={schedule.status} /></td>
        <td className="py-2 px-3 flex gap-1">
          <Button variant="outline" size="sm" onClick={() => runNow.mutate()} disabled={runNow.isPending}>
            <Play className="h-3 w-3" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => toggle.mutate()}>
            {schedule.status === "ACTIVE" ? "Pause" : "Resume"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => del.mutate()}>
            <Trash2 className="h-3 w-3 text-destructive" />
          </Button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="bg-secondary/20 px-6 py-3">
            {history.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                No runs recorded yet. {runNow.isPending ? "Running…" : "Click ▶ to run now."}
              </div>
            ) : (
              <div className="space-y-1">
                <div className="eyebrow">Run history (last {history.length})</div>
                <table className="w-full text-xs">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="text-left font-semibold py-1.5">Started</th>
                      <th className="text-left font-semibold py-1.5">Status</th>
                      <th className="text-left font-semibold py-1.5">Summary</th>
                      <th className="text-left font-semibold py-1.5">Alert</th>
                      <th className="text-right font-semibold py-1.5">Open</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {history.slice(0, 30).map((r) => {
                      const target = targetForRun(r.summary);
                      return (
                        <tr
                          key={r.id}
                          className={`${target ? "cursor-pointer hover:bg-secondary/40" : ""}`}
                          onClick={() => target && navigate(target)}
                        >
                          <td className="py-1.5 font-mono">
                            {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                          </td>
                          <td className="py-1.5"><StatusBadge status={r.status} /></td>
                          <td className="py-1.5 text-muted-foreground">
                            {r.summary.error ? (
                              <span className="text-destructive">{r.summary.error}</span>
                            ) : r.summary.templates_run !== undefined ? (
                              <>
                                {r.summary.templates_run} templates
                                {r.summary.max_score !== undefined &&
                                  ` · max ${r.summary.max_score.toFixed(1)}`}
                              </>
                            ) : r.summary.findings !== undefined ? (
                              <>{r.summary.findings} findings</>
                            ) : "—"}
                          </td>
                          <td className="py-1.5">
                            {r.alert_sent ? (
                              <span className="text-success">Sent</span>
                            ) : r.alert_error ? (
                              <span className="text-destructive" title={r.alert_error}>Failed</span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="py-1.5 text-right">
                            {target ? (
                              <span className="text-accent">→</span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function CreateScheduleDialog({
  projectId, onClose, onCreated,
}: { projectId: string; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"PACK" | "TEMPLATE">("PACK");
  const [code, setCode] = useState("AP_STANDARD");
  const [cron, setCron] = useState("0 2 1 * *");
  const [datasetId, setDatasetId] = useState("");
  const [alertEnabled, setAlertEnabled] = useState(false);
  const [alertThreshold, setAlertThreshold] = useState(80);
  const [recipients, setRecipients] = useState("");

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.get<Array<{ id: string; name: string }>>(
      `/api/datasets?project_id=${projectId}`,
    ),
  });

  const mutation = useMutation({
    mutationFn: () => api.post<Schedule>("/api/schedules", {
      name, project_id: projectId, dataset_id: datasetId || null,
      kind, pack_code: kind === "PACK" ? code : null,
      template_code: kind === "TEMPLATE" ? code : null,
      cron_expr: cron,
      alert_enabled: alertEnabled, alert_min_score: alertThreshold,
      alert_recipients: recipients.split(",").map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: onCreated,
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50 overflow-auto">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg my-8">
        <div className="p-5 border-b"><h3 className="text-base font-semibold">New schedule</h3></div>
        <div className="p-5 space-y-4">
          <div><Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)}
                   placeholder="Monthly AP Review" autoFocus /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Kind</Label>
              <Select value={kind} onChange={(e) => setKind(e.target.value as "PACK" | "TEMPLATE")}>
                <option value="PACK">Pack</option>
                <option value="TEMPLATE">Template</option>
              </Select></div>
            <div><Label>Code</Label>
              <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} /></div>
          </div>
          <div><Label>Cron expression</Label>
            <Input value={cron} onChange={(e) => setCron(e.target.value)}
                   className="font-mono" />
            <div className="text-xs text-muted-foreground mt-1">
              Min Hour Day Month DayOfWeek — e.g. <code className="bg-secondary px-1 rounded">0 2 1 * *</code> = 02:00 on the 1st
            </div>
          </div>
          <div><Label>Dataset</Label>
            <Select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">Pick a dataset…</option>
              {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select></div>
          <div className="rounded-md border border-dashed p-3 space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={alertEnabled}
                     onChange={(e) => setAlertEnabled(e.target.checked)} />
              Send email alert when max risk score ≥ threshold
            </label>
            {alertEnabled && (
              <>
                <div>
                  <Label>Threshold (0–100)</Label>
                  <Input type="number" value={alertThreshold}
                         onChange={(e) => setAlertThreshold(Number(e.target.value))} />
                </div>
                <div>
                  <Label>Recipients (comma-separated emails)</Label>
                  <Input value={recipients} onChange={(e) => setRecipients(e.target.value)} />
                </div>
              </>
            )}
          </div>
          {mutation.isError && (
            <div className="text-sm text-destructive">{(mutation.error as Error).message}</div>
          )}
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!name || mutation.isPending}>
            {mutation.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
