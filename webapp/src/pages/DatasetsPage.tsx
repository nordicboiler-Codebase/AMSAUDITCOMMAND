import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Download, FileSearch, Play, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, getToken, type Dataset, type Finding, type TestRun } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatNumber } from "@/lib/utils";

const SUBLEDGERS = [
  "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "GENERAL_LEDGER", "PAYROLL",
  "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
];

const CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"];

export function DatasetsPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Dataset | null>(null);

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () => api.get<Dataset[]>(
      `/api/datasets${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
  });

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Datasets" description="Raw source data, hashed + Fernet-encrypted at rest." />
        <EmptyState
          icon={<Database className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the sidebar to see its datasets."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Datasets"
        description="Raw source data, SHA-256 hashed on import, Fernet-encrypted at rest."
        actions={<Button onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Import</Button>}
      />

      <SampleDownloads />

      {datasets.length === 0 ? (
        <EmptyState
          icon={<Database className="h-5 w-5" />}
          title="No datasets imported"
          description="Import a CSV or Excel file to start analysing."
          action={<Button onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Import first dataset</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SectionCard className="lg:col-span-2" title={`${datasets.length} datasets`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left font-semibold py-2 px-3">Name</th>
                    <th className="text-left font-semibold py-2 px-3">Subledger</th>
                    <th className="text-right font-semibold py-2 px-3">Rows</th>
                    <th className="text-left font-semibold py-2 px-3">File</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {datasets.map((d) => (
                    <tr
                      key={d.id}
                      onClick={() => setSelected(d)}
                      className={`cursor-pointer hover:bg-secondary/30 ${
                        selected?.id === d.id ? "bg-secondary/50" : ""
                      }`}
                    >
                      <td className="py-2 px-3 font-medium">{d.name}</td>
                      <td className="py-2 px-3">
                        <Badge tone="muted">{d.subledger_type.replace(/_/g, " ")}</Badge>
                      </td>
                      <td className="py-2 px-3 text-right tabular-nums">{formatNumber(d.record_count)}</td>
                      <td className="py-2 px-3 text-xs text-muted-foreground truncate max-w-[200px]">
                        {d.source_filename}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
          <DatasetDetail dataset={selected} />
        </div>
      )}

      {open && (
        <ImportDialog
          projectId={activeProjectId}
          onClose={() => setOpen(false)}
          onImported={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["datasets"] });
          }}
        />
      )}
    </>
  );
}

function DatasetDetail({ dataset }: { dataset: Dataset | null }) {
  const navigate = useNavigate();
  const { data: preview } = useQuery({
    queryKey: ["dataset-preview", dataset?.id],
    queryFn: () => api.get<{ columns: string[]; rows: Array<Record<string, unknown>> }>(
      `/api/datasets/${dataset!.id}/preview?rows=20`,
    ),
    enabled: !!dataset,
  });
  const { data: runs = [] } = useQuery({
    queryKey: ["dataset-runs", dataset?.id],
    queryFn: () => api.get<TestRun[]>(`/api/datasets/${dataset!.id}/runs`),
    enabled: !!dataset,
  });
  const { data: findings = [] } = useQuery({
    queryKey: ["dataset-findings", dataset?.id],
    queryFn: () => api.get<Finding[]>(`/api/findings?dataset_id=${dataset!.id}&limit=200`),
    enabled: !!dataset,
  });
  if (!dataset) {
    return (
      <SectionCard title="Detail">
        <div className="text-sm text-muted-foreground py-10 text-center">
          Select a dataset to see its preview and hashes.
        </div>
      </SectionCard>
    );
  }
  return (
    <SectionCard title={dataset.name}>
      <div className="space-y-2 text-xs">
        <InfoRow label="Rows" value={formatNumber(dataset.record_count)} />
        <InfoRow label="Subledger" value={dataset.subledger_type.replace(/_/g, " ")} />
        <InfoRow label="Source" value={dataset.source_filename} mono />
        <InfoRow label="SHA-256" value={dataset.source_hash.slice(0, 24) + "…"} mono />
        <InfoRow label="Dataset ID" value={dataset.id.slice(0, 8) + "…"} mono />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Button
          variant="accent" size="sm"
          onClick={() => {
            localStorage.setItem("ts_active_dataset", dataset.id);
            navigate("/run");
          }}
        >
          <Play className="h-3.5 w-3.5" /> Run tests
        </Button>
        <Button
          variant="outline" size="sm"
          onClick={() => {
            localStorage.setItem("ts_active_dataset", dataset.id);
            navigate("/risk");
          }}
        >
          Risk Explorer
        </Button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        <button
          onClick={() => navigate(`/runs?dataset=${dataset.id}`)}
          className="rounded-md border bg-secondary/30 hover:bg-secondary p-2.5 text-left"
        >
          <div className="font-bold tabular-nums text-base">{runs.length}</div>
          <div className="text-muted-foreground">Test runs →</div>
        </button>
        <button
          onClick={() => navigate(`/findings?dataset=${dataset.id}`)}
          className="rounded-md border bg-secondary/30 hover:bg-secondary p-2.5 text-left"
        >
          <div className="font-bold tabular-nums text-base">{findings.length}</div>
          <div className="text-muted-foreground flex items-center gap-1">
            <FileSearch className="h-3 w-3" /> Findings →
          </div>
        </button>
      </div>
      {preview && preview.rows.length > 0 && (
        <div className="mt-4">
          <div className="eyebrow mb-2">Preview (first 20)</div>
          <div className="overflow-x-auto max-h-[280px] border rounded-md">
            <table className="w-full text-xs">
              <thead className="bg-secondary sticky top-0">
                <tr>
                  {preview.columns.slice(0, 5).map((c) => (
                    <th key={c} className="text-left font-semibold py-1.5 px-2 border-r last:border-r-0">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {preview.rows.slice(0, 20).map((r, i) => (
                  <tr key={i}>
                    {preview.columns.slice(0, 5).map((c) => (
                      <td key={c} className="py-1 px-2 truncate max-w-[120px] font-mono">
                        {String(r[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono truncate" : "truncate"}>{value}</span>
    </div>
  );
}

interface Sample {
  filename: string;
  title: string;
  description: string;
  subledger_type: string;
  suggested_pack: string;
  size_bytes: number;
}

function SampleDownloads() {
  const [open, setOpen] = useState(false);
  const { toast } = useToast();
  const { data: samples = [] } = useQuery({
    queryKey: ["samples"],
    queryFn: () => api.get<Sample[]>("/api/samples"),
  });

  async function downloadSample(s: Sample) {
    try {
      const r = await fetch(`/api/samples/${s.filename}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) throw new Error(r.statusText);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = s.filename; a.click();
      URL.revokeObjectURL(url);
      toast({
        kind: "success",
        title: `Downloaded ${s.filename}`,
        description: `Import it back, then run pack ${s.suggested_pack}`,
      });
    } catch (e) {
      toast({ kind: "error", title: "Download failed", description: (e as Error).message });
    }
  }

  if (!samples.length) return null;

  return (
    <SectionCard
      title="Sample CSVs (planted fraud signals)"
      description="Download a ready-made file, import it, then run the suggested pack — findings light up immediately."
      actions={
        <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide samples" : `Browse ${samples.length} samples`}
        </Button>
      }
    >
      {open && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mt-2">
          {samples.map((s) => (
            <div
              key={s.filename}
              className="rounded-lg border bg-card p-3.5 hover:shadow-sm transition-shadow"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Badge tone="muted">{s.subledger_type.replace(/_/g, " ")}</Badge>
                  <div className="text-sm font-semibold mt-2">{s.title}</div>
                </div>
              </div>
              <div className="text-xs text-muted-foreground mt-1.5 line-clamp-2">
                {s.description}
              </div>
              <div className="text-[11px] text-muted-foreground mt-2 font-mono">
                Suggested pack: {s.suggested_pack}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="w-full mt-3"
                onClick={() => downloadSample(s)}
              >
                <Download className="h-3.5 w-3.5" /> {s.filename}
              </Button>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function ImportDialog({
  projectId, onClose, onImported,
}: { projectId: string; onClose: () => void; onImported: () => void }) {
  const [name, setName] = useState("");
  const [subledger, setSubledger] = useState("ACCOUNTS_PAYABLE");
  const [classification, setClassification] = useState("INTERNAL");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Pick a file");
      const form = new FormData();
      form.append("file", file);
      form.append("project_id", projectId);
      form.append("name", name);
      form.append("subledger_type", subledger);
      form.append("classification", classification);
      if (description) form.append("description", description);
      return api.post("/api/datasets/import", form);
    },
    onSuccess: onImported,
    onError: (e) => setError((e as Error).message),
  });

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-xl rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b">
          <h3 className="text-base font-semibold">Import dataset</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            CSV or Excel. File is SHA-256 hashed, stored encrypted.
          </p>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <Label>Dataset name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="AP — March 2026" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Subledger</Label>
              <Select value={subledger} onChange={(e) => setSubledger(e.target.value)}>
                {SUBLEDGERS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </Select>
            </div>
            <div>
              <Label>Classification</Label>
              <Select value={classification} onChange={(e) => setClassification(e.target.value)}>
                {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </div>
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <div>
            <Label>File</Label>
            <div
              className="border-2 border-dashed border-border rounded-md p-6 text-center cursor-pointer hover:bg-secondary/30"
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="h-6 w-6 mx-auto text-muted-foreground" />
              <div className="text-sm mt-2">
                {file ? <span className="font-medium">{file.name}</span> : "Click to pick a file"}
              </div>
              <div className="text-xs text-muted-foreground mt-1">CSV, XLSX, Parquet up to 200MB</div>
              <input
                ref={fileRef} type="file" className="hidden"
                accept=".csv,.xlsx,.xls,.parquet"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!name || !file || mutation.isPending}>
            {mutation.isPending ? "Uploading…" : "Import"}
          </Button>
        </div>
      </div>
    </div>
  );
}
