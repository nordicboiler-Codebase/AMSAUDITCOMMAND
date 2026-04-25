import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Pause, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface Monitor {
  id: string;
  project_id: string;
  name: string;
  subledger_type: string;
  pack_code: string;
  auto_ensemble: boolean;
  auto_create_finding_min_score: number;
  alert_recipients: string[];
  enabled: boolean;
  last_triggered_at?: string;
  last_dataset_id?: string;
}

const SUBLEDGERS = [
  "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "GENERAL_LEDGER", "PAYROLL",
  "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
];

export function MonitorsPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: monitors = [] } = useQuery({
    queryKey: ["monitors", activeProjectId],
    queryFn: () => api.get<Monitor[]>(
      `/api/monitors${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
    enabled: !!activeProjectId,
  });

  if (!activeProjectId) {
    return (
      <>
        <PageHeader
          title="Continuous monitoring"
          description="Auto-run a pack the moment a new dataset arrives — for the matched subledger."
        />
        <EmptyState
          icon={<Activity className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the top bar."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Continuous monitoring"
        description="Each monitor watches a subledger. When a new dataset of that type imports, the chosen pack runs + ensemble auto-creates DRAFT findings above the threshold."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New monitor</Button>}
      />
      {monitors.length === 0 ? (
        <EmptyState
          icon={<Activity className="h-5 w-5" />}
          title="No monitors configured"
          description="Add a monitor to auto-run AP_STANDARD whenever you import a new accounts-payable dataset."
          action={<Button onClick={() => setOpen(true)}>Create monitor</Button>}
        />
      ) : (
        <SectionCard title={`${monitors.length} monitors`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Name</th>
                  <th className="text-left font-semibold py-2 px-3">Subledger</th>
                  <th className="text-left font-semibold py-2 px-3">Pack</th>
                  <th className="text-right font-semibold py-2 px-3">Auto-find threshold</th>
                  <th className="text-left font-semibold py-2 px-3">Alerts</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-left font-semibold py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {monitors.map((m) => (
                  <MonitorRow
                    key={m.id} monitor={m}
                    onChange={() => qc.invalidateQueries({ queryKey: ["monitors"] })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {open && (
        <CreateMonitorDialog
          projectId={activeProjectId}
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["monitors"] });
          }}
        />
      )}
    </>
  );
}

function MonitorRow({ monitor, onChange }: { monitor: Monitor; onChange: () => void }) {
  const { toast } = useToast();
  const toggle = useMutation({
    mutationFn: () => api.patch(`/api/monitors/${monitor.id}`, { enabled: !monitor.enabled }),
    onSuccess: () => {
      toast({ kind: "success", title: monitor.enabled ? "Paused" : "Enabled" });
      onChange();
    },
  });
  const del = useMutation({
    mutationFn: () => api.delete(`/api/monitors/${monitor.id}`),
    onSuccess: () => { toast({ kind: "success", title: "Monitor removed" }); onChange(); },
  });
  return (
    <tr className="hover:bg-secondary/30">
      <td className="py-2 px-3 font-medium">{monitor.name}</td>
      <td className="py-2 px-3"><Badge tone="muted">{monitor.subledger_type.replace(/_/g, " ")}</Badge></td>
      <td className="py-2 px-3 font-mono text-xs">{monitor.pack_code}</td>
      <td className="py-2 px-3 text-right tabular-nums">
        ≥ {monitor.auto_create_finding_min_score.toFixed(0)}
      </td>
      <td className="py-2 px-3 text-xs text-muted-foreground">
        {monitor.alert_recipients.length
          ? `${monitor.alert_recipients.length} recipient${monitor.alert_recipients.length === 1 ? "" : "s"}`
          : "Off"}
      </td>
      <td className="py-2 px-3">
        <StatusBadge status={monitor.enabled ? "ACTIVE" : "PAUSED"} />
      </td>
      <td className="py-2 px-3 flex gap-1">
        <Button variant="outline" size="sm" onClick={() => toggle.mutate()}>
          {monitor.enabled ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
        </Button>
        <Button variant="outline" size="sm" onClick={() => del.mutate()}>
          <Trash2 className="h-3 w-3 text-destructive" />
        </Button>
      </td>
    </tr>
  );
}

function CreateMonitorDialog({
  projectId, onClose, onCreated,
}: { projectId: string; onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [subledger, setSubledger] = useState("ACCOUNTS_PAYABLE");
  const [packCode, setPackCode] = useState("AP_STANDARD");
  const [autoEnsemble, setAutoEnsemble] = useState(true);
  const [threshold, setThreshold] = useState(90);
  const [recipients, setRecipients] = useState("");

  const mutation = useMutation({
    mutationFn: () => api.post("/api/monitors", {
      project_id: projectId,
      name, subledger_type: subledger, pack_code: packCode,
      auto_ensemble: autoEnsemble,
      auto_create_finding_min_score: threshold,
      alert_recipients: recipients.split(",").map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: () => {
      toast({ kind: "success", title: "Monitor created" });
      onCreated();
    },
    onError: (e) => toast({ kind: "error", title: "Failed", description: (e as Error).message }),
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b">
          <h3 className="text-base font-semibold">New monitor</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Fires when a dataset of this subledger is imported into this project.
          </p>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)}
                   placeholder="AP — auto-screen on import" autoFocus />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Subledger</Label>
              <Select value={subledger} onChange={(e) => setSubledger(e.target.value)}>
                {SUBLEDGERS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </Select>
            </div>
            <div>
              <Label>Pack code</Label>
              <Input value={packCode} onChange={(e) => setPackCode(e.target.value.toUpperCase())} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox" id="ae" checked={autoEnsemble}
              onChange={(e) => setAutoEnsemble(e.target.checked)}
            />
            <Label htmlFor="ae" className="mb-0">Compute ensemble + auto-create DRAFT findings</Label>
          </div>
          {autoEnsemble && (
            <>
              <div>
                <Label>Auto-create finding when score ≥ ({threshold})</Label>
                <input
                  type="range" min={0} max={100} value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  className="w-full accent-accent"
                />
              </div>
              <div>
                <Label>Alert recipients (comma-separated emails)</Label>
                <Input value={recipients} onChange={(e) => setRecipients(e.target.value)}
                       placeholder="auditor@example.com" />
              </div>
            </>
          )}
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!name || mutation.isPending}>
            {mutation.isPending ? "Creating…" : "Create monitor"}
          </Button>
        </div>
      </div>
    </div>
  );
}
