import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSearch, Filter } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, MetricCard, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, type Finding } from "@/lib/api";

const STATUSES = [
  "", "DRAFT", "UNDER_REVIEW", "CONFIRMED", "FALSE_POSITIVE",
  "REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD",
];
const SEVERITIES = ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"];

export function FindingsPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [open, setOpen] = useState(false);

  const query = useQuery({
    queryKey: ["findings", activeProjectId, status, severity],
    queryFn: () => {
      const params = new URLSearchParams();
      if (activeProjectId) params.set("project_id", activeProjectId);
      if (status) params.set("status", status);
      if (severity) params.set("severity", severity);
      return api.get<Finding[]>(`/api/findings?${params.toString()}`);
    },
    enabled: !!activeProjectId,
  });
  const findings = query.data ?? [];

  const countsBySeverity = findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.severity] = (acc[f.severity] || 0) + 1;
    return acc;
  }, {});

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Findings" description="Every flagged issue. Maker-checker enforced." />
        <EmptyState
          icon={<FileSearch className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the sidebar to see findings."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Findings"
        description="Every flagged issue. Maker creates DRAFT; an independent reviewer confirms/closes."
        actions={<Button onClick={() => setOpen(true)}>Create finding</Button>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard label="Critical" value={countsBySeverity.CRITICAL || 0} accent="#821b1a" />
        <MetricCard label="High" value={countsBySeverity.HIGH || 0} accent="#c2342f" />
        <MetricCard label="Medium" value={countsBySeverity.MEDIUM || 0} accent="#b76e00" />
        <MetricCard label="Low" value={countsBySeverity.LOW || 0} accent="#0f766e" />
      </div>

      <SectionCard
        actions={
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-32">
              {SEVERITIES.map((s) => <option key={s || "any"} value={s}>{s || "All severities"}</option>)}
            </Select>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
              {STATUSES.map((s) => <option key={s || "any"} value={s}>{s ? s.replace(/_/g, " ") : "All statuses"}</option>)}
            </Select>
          </div>
        }
      >
        {findings.length === 0 ? (
          <EmptyState
            icon={<FileSearch className="h-5 w-5" />}
            title="No findings in this filter"
            description="Create the first finding or relax the filter."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-secondary/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Code</th>
                  <th className="text-left font-semibold py-2 px-3">Title</th>
                  <th className="text-left font-semibold py-2 px-3">Severity</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-right font-semibold py-2 px-3">Risk</th>
                  <th className="text-left font-semibold py-2 px-3">Due</th>
                  <th className="text-left font-semibold py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {findings.map((f) => (
                  <FindingRow key={f.id} finding={f} onTransition={() => qc.invalidateQueries({ queryKey: ["findings"] })} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {open && activeProjectId && (
        <CreateFindingDialog
          projectId={activeProjectId}
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["findings"] });
          }}
        />
      )}
    </>
  );
}

function FindingRow({ finding, onTransition }: { finding: Finding; onTransition: () => void }) {
  const mutation = useMutation({
    mutationFn: (status: string) =>
      api.post(`/api/findings/${finding.id}/transition`, { status }),
    onSuccess: onTransition,
  });
  const nextStatuses: Record<string, string[]> = {
    DRAFT: ["UNDER_REVIEW", "FALSE_POSITIVE"],
    UNDER_REVIEW: ["CONFIRMED", "FALSE_POSITIVE", "DRAFT"],
    CONFIRMED: ["REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD"],
  };
  const next = nextStatuses[finding.status] || [];

  return (
    <tr className="hover:bg-secondary/30">
      <td className="py-2 px-3 font-mono text-xs font-medium">{finding.code}</td>
      <td className="py-2 px-3 truncate max-w-[420px]">{finding.title}</td>
      <td className="py-2 px-3"><SeverityBadge severity={finding.severity} /></td>
      <td className="py-2 px-3"><StatusBadge status={finding.status} /></td>
      <td className="py-2 px-3 text-right tabular-nums">
        {finding.risk_score?.toFixed(1) ?? "—"}
      </td>
      <td className="py-2 px-3 text-muted-foreground text-xs">{finding.due_date ?? "—"}</td>
      <td className="py-2 px-3">
        {next.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {next.map((s) => (
              <button
                key={s}
                disabled={mutation.isPending}
                onClick={() => mutation.mutate(s)}
                className="text-[11px] px-2 py-0.5 rounded border border-border bg-card hover:bg-secondary"
              >
                → {s.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

function CreateFindingDialog({
  projectId, onClose, onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("MEDIUM");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => api.post<Finding>("/api/findings", {
      project_id: projectId, title, description, severity,
    }),
    onSuccess: onCreated,
    onError: (e) => setError((e as Error).message),
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b">
          <h3 className="text-base font-semibold">Create finding</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Drafts. An independent reviewer must confirm or close.
          </p>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} />
          </div>
          <div>
            <Label>Severity</Label>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!title || mutation.isPending}>
            {mutation.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
