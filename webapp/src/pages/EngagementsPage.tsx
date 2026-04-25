import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Download, FileSearch, FolderKanban, Play, Plus, X } from "lucide-react";
import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api, getToken, type Dataset, type Finding, type TestRun } from "@/lib/api";
import { useToast } from "@/lib/toast";

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

          <EngagementDetail
            engagement={selected}
            projectId={activeProjectId}
            onUpdate={() => qc.invalidateQueries({ queryKey: ["engagements"] })}
          />
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
  engagement, projectId, onUpdate,
}: { engagement: Engagement | null; projectId: string; onUpdate: () => void }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [picker, setPicker] = useState<"dataset" | "finding" | null>(null);

  const mutation = useMutation({
    mutationFn: (status: string) =>
      api.post(`/api/engagements/${engagement!.id}/transition`, { status }),
    onSuccess: onUpdate,
  });

  const addArtifact = useMutation({
    mutationFn: (vars: { kind: string; ref_id: string }) =>
      api.post(`/api/engagements/${engagement!.id}/artifact`, vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engagements"] });
      toast({ kind: "success", title: "Linked to engagement" });
      setPicker(null);
    },
    onError: (e) => toast({ kind: "error", title: "Could not link", description: (e as Error).message }),
  });

  const removeArtifact = useMutation({
    mutationFn: (vars: { kind: "dataset_ids" | "pack_run_ids" | "finding_ids"; ref_id: string }) => {
      const current =
        vars.kind === "dataset_ids" ? engagement!.dataset_ids :
        vars.kind === "pack_run_ids" ? engagement!.pack_run_ids :
        engagement!.finding_ids;
      const next = current.filter((x) => x !== vars.ref_id);
      return api.patch(`/api/engagements/${engagement!.id}`, { [vars.kind]: next });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engagements"] });
      toast({ kind: "success", title: "Unlinked" });
    },
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

      <ArtifactList
        title="Datasets" icon={<Database className="h-3.5 w-3.5" />}
        ids={engagement.dataset_ids}
        onAdd={engagement.status !== "FINALISED" && engagement.status !== "ARCHIVED"
          ? () => setPicker("dataset") : undefined}
        onClick={() => navigate("/datasets")}
        onRemove={(rid) => removeArtifact.mutate({ kind: "dataset_ids", ref_id: rid })}
      />

      <ArtifactList
        title="Pack runs" icon={<Play className="h-3.5 w-3.5" />}
        ids={engagement.pack_run_ids}
        onClick={(id) => navigate(`/packs/runs/${id}`)}
        onRemove={(rid) => removeArtifact.mutate({ kind: "pack_run_ids", ref_id: rid })}
        emptyHint="Pack runs auto-link when initiated from a pack with this engagement."
      />

      <ArtifactList
        title="Findings" icon={<FileSearch className="h-3.5 w-3.5" />}
        ids={engagement.finding_ids}
        onAdd={engagement.status !== "FINALISED" && engagement.status !== "ARCHIVED"
          ? () => setPicker("finding") : undefined}
        onClick={(id) => navigate(`/findings/${id}`)}
        onRemove={(rid) => removeArtifact.mutate({ kind: "finding_ids", ref_id: rid })}
      />

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

      {picker === "dataset" && (
        <DatasetPicker
          projectId={projectId}
          excludeIds={engagement.dataset_ids}
          onPick={(id) => addArtifact.mutate({ kind: "dataset", ref_id: id })}
          onClose={() => setPicker(null)}
        />
      )}
      {picker === "finding" && (
        <FindingPicker
          projectId={projectId}
          excludeIds={engagement.finding_ids}
          onPick={(id) => addArtifact.mutate({ kind: "finding", ref_id: id })}
          onClose={() => setPicker(null)}
        />
      )}
    </SectionCard>
  );
}

function ArtifactList({
  title, icon, ids, onAdd, onClick, onRemove, emptyHint,
}: {
  title: string;
  icon: React.ReactNode;
  ids: string[];
  onAdd?: () => void;
  onClick?: (id: string) => void;
  onRemove?: (id: string) => void;
  emptyHint?: string;
}) {
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <div className="eyebrow flex items-center gap-1.5">
          {icon} {title} ({ids.length})
        </div>
        {onAdd && (
          <button onClick={onAdd}
                  className="text-[11px] text-accent hover:underline flex items-center gap-1">
            <Plus className="h-3 w-3" /> Add
          </button>
        )}
      </div>
      {ids.length === 0 ? (
        <div className="text-[11px] text-muted-foreground italic mt-1">
          {emptyHint || "None linked."}
        </div>
      ) : (
        <div className="mt-1 space-y-0.5">
          {ids.slice(0, 8).map((id) => (
            <div key={id} className="flex items-center gap-1 text-[11px] font-mono group">
              <button
                disabled={!onClick}
                onClick={() => onClick?.(id)}
                className="flex-1 truncate text-left rounded px-1.5 py-0.5 hover:bg-secondary disabled:cursor-default"
              >
                {id.slice(0, 18)}…
              </button>
              {onRemove && (
                <button
                  onClick={() => onRemove(id)}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive p-0.5"
                  title="Unlink"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
          {ids.length > 8 && (
            <div className="text-[10px] text-muted-foreground px-1.5">
              +{ids.length - 8} more…
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DatasetPicker({
  projectId, excludeIds, onPick, onClose,
}: {
  projectId: string;
  excludeIds: string[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.get<Dataset[]>(`/api/datasets?project_id=${projectId}`),
  });
  const exclude = new Set(excludeIds);
  const filtered = datasets
    .filter((d) => !exclude.has(d.id))
    .filter((d) => !q || d.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <PickerModal
      title="Link a dataset"
      hint="Source data for this engagement."
      query={q} setQuery={setQ}
      onClose={onClose}
    >
      {filtered.length === 0 ? (
        <div className="text-xs text-muted-foreground italic p-3">
          {datasets.length === 0 ? "No datasets in this project." : "All datasets are already linked."}
        </div>
      ) : (
        <div className="divide-y">
          {filtered.map((d) => (
            <button
              key={d.id}
              onClick={() => onPick(d.id)}
              className="w-full text-left p-2 hover:bg-secondary/30"
            >
              <div className="text-sm font-medium">{d.name}</div>
              <div className="text-[11px] text-muted-foreground">
                {d.subledger_type.replace(/_/g, " ")} · {d.record_count.toLocaleString()} rows
              </div>
            </button>
          ))}
        </div>
      )}
    </PickerModal>
  );
}

function FindingPicker({
  projectId, excludeIds, onPick, onClose,
}: {
  projectId: string;
  excludeIds: string[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const { data: findings = [] } = useQuery({
    queryKey: ["findings-picker", projectId],
    queryFn: () => api.get<Finding[]>(`/api/findings?project_id=${projectId}&limit=500`),
  });
  const exclude = new Set(excludeIds);
  const filtered = findings
    .filter((f) => !exclude.has(f.id))
    .filter((f) => !q ||
      f.code.toLowerCase().includes(q.toLowerCase()) ||
      f.title.toLowerCase().includes(q.toLowerCase()),
    );

  return (
    <PickerModal
      title="Link a finding"
      hint="Pull existing findings into this engagement's scope."
      query={q} setQuery={setQ}
      onClose={onClose}
    >
      {filtered.length === 0 ? (
        <div className="text-xs text-muted-foreground italic p-3">No findings to link.</div>
      ) : (
        <div className="divide-y">
          {filtered.slice(0, 50).map((f) => (
            <button
              key={f.id}
              onClick={() => onPick(f.id)}
              className="w-full text-left p-2 hover:bg-secondary/30 flex items-center gap-2"
            >
              <div className="font-mono text-[11px] font-semibold w-20 shrink-0">{f.code}</div>
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{f.title}</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <SeverityBadge severity={f.severity} />
                  <StatusBadge status={f.status} />
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </PickerModal>
  );
}

function PickerModal({
  title, hint, query, setQuery, onClose, children,
}: {
  title: string;
  hint: string;
  query: string;
  setQuery: (v: string) => void;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
         onClick={onClose}>
      <div className="w-full max-w-md rounded-lg bg-card border shadow-lg flex flex-col max-h-[80vh]"
           onClick={(e) => e.stopPropagation()}>
        <div className="p-4 border-b">
          <h3 className="text-base font-semibold">{title}</h3>
          <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>
          <Input
            placeholder="Search…"
            className="mt-3"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex-1 overflow-auto">{children}</div>
        <div className="p-3 border-t flex justify-end">
          <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
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
