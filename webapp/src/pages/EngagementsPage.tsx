import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus, Download } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api, getToken } from "@/lib/api";

interface Engagement {
  id: string;
  code: string;
  title: string;
  project_id: string;
  period_start?: string;
  period_end?: string;
  scope?: string;
  status: string;
  dataset_ids: string[];
  pack_run_ids: string[];
  finding_ids: string[];
  executive_summary?: string;
  finalised_at?: string;
}

export function EngagementsPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Engagement | null>(null);

  const { data: engagements = [] } = useQuery({
    queryKey: ["engagements", activeProjectId],
    queryFn: () => api.get<Engagement[]>(
      `/api/engagements${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
    enabled: !!activeProjectId,
  });

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Engagements" description="Group an audit period's work." />
        <EmptyState
          icon={<FolderKanban className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the sidebar first."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Engagements"
        description="Wrap a period's datasets, pack runs, findings into one audit engagement with maker-checker finalise."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New engagement</Button>}
      />

      {engagements.length === 0 ? (
        <EmptyState
          icon={<FolderKanban className="h-5 w-5" />}
          title="No engagements yet"
          description="Create one to group this period's audit work."
          action={<Button onClick={() => setOpen(true)}>Create engagement</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SectionCard className="lg:col-span-2" title={`${engagements.length} engagements`}>
            <div className="divide-y">
              {engagements.map((e) => (
                <div
                  key={e.id}
                  onClick={() => setSelected(e)}
                  className={`py-3 px-2 cursor-pointer hover:bg-secondary/30 rounded-md ${
                    selected?.id === e.id ? "bg-secondary/50" : ""
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-mono text-xs font-semibold">{e.code}</div>
                    <StatusBadge status={e.status} />
                  </div>
                  <div className="font-medium text-sm mt-0.5">{e.title}</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {e.period_start ?? "—"} → {e.period_end ?? "—"} ·{" "}
                    {e.dataset_ids.length} ds · {e.pack_run_ids.length} packs ·{" "}
                    {e.finding_ids.length} findings
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <EngagementDetail engagement={selected} onUpdate={() =>
            qc.invalidateQueries({ queryKey: ["engagements"] })
          } />
        </div>
      )}

      {open && (
        <CreateEngagementDialog
          projectId={activeProjectId}
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["engagements"] });
          }}
        />
      )}
    </>
  );
}

function EngagementDetail({
  engagement, onUpdate,
}: { engagement: Engagement | null; onUpdate: () => void }) {
  const mutation = useMutation({
    mutationFn: (status: string) =>
      api.post(`/api/engagements/${engagement!.id}/transition`, { status }),
    onSuccess: onUpdate,
  });
  if (!engagement) {
    return (
      <SectionCard title="Detail">
        <div className="text-sm text-muted-foreground py-10 text-center">
          Select an engagement.
        </div>
      </SectionCard>
    );
  }
  const nexts: Record<string, string[]> = {
    PLANNING: ["IN_PROGRESS", "ARCHIVED"],
    IN_PROGRESS: ["REVIEW", "PLANNING"],
    REVIEW: ["FINALISED", "IN_PROGRESS"],
    FINALISED: ["ARCHIVED"],
  };
  const available = nexts[engagement.status] || [];

  return (
    <SectionCard title={engagement.code}>
      <div className="text-base font-semibold">{engagement.title}</div>
      <div className="text-xs text-muted-foreground mt-1">
        {engagement.period_start} → {engagement.period_end}
      </div>
      <div className="mt-3"><StatusBadge status={engagement.status} /></div>
      {engagement.scope && (
        <>
          <div className="eyebrow mt-4 mb-1">Scope</div>
          <div className="text-sm">{engagement.scope}</div>
        </>
      )}

      <div className="grid grid-cols-3 gap-2 mt-4 text-center">
        <div className="rounded-md bg-secondary p-2">
          <div className="text-lg font-bold tabular-nums">{engagement.dataset_ids.length}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Datasets</div>
        </div>
        <div className="rounded-md bg-secondary p-2">
          <div className="text-lg font-bold tabular-nums">{engagement.pack_run_ids.length}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Pack runs</div>
        </div>
        <div className="rounded-md bg-secondary p-2">
          <div className="text-lg font-bold tabular-nums">{engagement.finding_ids.length}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Findings</div>
        </div>
      </div>

      {available.length > 0 && (
        <div className="mt-5">
          <div className="eyebrow mb-2">Transition</div>
          <div className="flex flex-wrap gap-1.5">
            {available.map((s) => (
              <Button key={s} variant="outline" size="sm"
                      onClick={() => mutation.mutate(s)} disabled={mutation.isPending}>
                → {s.replace(/_/g, " ")}
              </Button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5">
        <a
          href={`/api/engagements/${engagement.id}/workpaper.zip`}
          onClick={(e) => {
            e.preventDefault();
            const url = `/api/engagements/${engagement.id}/workpaper.zip`;
            fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
              .then((r) => r.blob())
              .then((blob) => {
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `${engagement.code}_workpaper.zip`;
                a.click();
              });
          }}
          className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
        >
          <Download className="h-3.5 w-3.5" /> Download workpaper bundle
        </a>
      </div>
    </SectionCard>
  );
}

function CreateEngagementDialog({
  projectId, onClose, onCreated,
}: { projectId: string; onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [scope, setScope] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const mutation = useMutation({
    mutationFn: () => api.post<Engagement>("/api/engagements", {
      project_id: projectId, title, scope,
      period_start: start || null, period_end: end || null,
    }),
    onSuccess: onCreated,
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b"><h3 className="text-base font-semibold">New engagement</h3></div>
        <div className="p-5 space-y-4">
          <div>
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                   placeholder="Q2 2026 AP Audit" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Period start</Label>
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div>
              <Label>Period end</Label>
              <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Scope</Label>
            <Textarea rows={3} value={scope} onChange={(e) => setScope(e.target.value)} />
          </div>
          {mutation.isError && (
            <div className="text-sm text-destructive">{(mutation.error as Error).message}</div>
          )}
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
