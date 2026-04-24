import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus } from "lucide-react";
import { useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, PageHeader } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, type Project, type Subsidiary } from "@/lib/api";

export function ProjectsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/api/projects"),
  });
  const { data: subs = [] } = useQuery({
    queryKey: ["subsidiaries"],
    queryFn: () => api.get<Subsidiary[]>("/api/subsidiaries"),
  });
  const subsMap = Object.fromEntries(subs.map((s) => [s.code, s]));

  return (
    <>
      <PageHeader
        title="Projects"
        description="An audit project scopes work to a subsidiary or cross-entity theme."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> New project
          </Button>
        }
      />
      {projects.length === 0 ? (
        <EmptyState
          icon={<FolderKanban className="h-5 w-5" />}
          title="No projects yet"
          description="Create your first audit project to start importing data and running packs."
          action={<Button onClick={() => setOpen(true)}>Create project</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {projects.map((p) => (
            <div key={p.id} className="rounded-lg border bg-card p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold text-sm truncate">{p.name}</div>
                <StatusBadge status={p.status} />
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {subsMap[p.subsidiary_code || ""]?.name || p.subsidiary_code || "No subsidiary"}
              </div>
              {p.description && (
                <div className="text-xs text-muted-foreground mt-3 line-clamp-2">
                  {p.description}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {open && <CreateProjectDialog subs={subs} onClose={() => setOpen(false)} onCreated={() => {
        setOpen(false);
        qc.invalidateQueries({ queryKey: ["projects"] });
      }} />}
    </>
  );
}

function CreateProjectDialog({
  subs, onClose, onCreated,
}: { subs: Subsidiary[]; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [subsidiaryCode, setSubsidiaryCode] = useState("");
  const mutation = useMutation({
    mutationFn: () => api.post<Project>("/api/projects", {
      name, description, subsidiary_code: subsidiaryCode || null,
    }),
    onSuccess: onCreated,
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b">
          <h3 className="text-base font-semibold">New project</h3>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus
                   placeholder="Q2 2026 AP Review — SUB-001" />
          </div>
          <div>
            <Label>Subsidiary</Label>
            <Select value={subsidiaryCode} onChange={(e) => setSubsidiaryCode(e.target.value)}>
              <option value="">(none)</option>
              {subs.map((s) => (
                <option key={s.id} value={s.code}>{s.code} — {s.name}</option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </div>
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
