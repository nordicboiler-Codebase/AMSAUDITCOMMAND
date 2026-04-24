import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

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

  return (
    <tr className="hover:bg-secondary/30">
      <td className="py-2 px-3 font-medium">{schedule.name}</td>
      <td className="py-2 px-3 font-mono text-xs">
        {schedule.kind}: {schedule.pack_code || schedule.template_code}
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
