import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Play, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, type TestRun } from "@/lib/api";
import { useToast } from "@/lib/toast";

type Tab = "template" | "pack" | "detector";

interface TemplateRow {
  code: string;
  name: string;
  detector_name: string;
  category: string;
  subledger_type?: string;
  default_weight: number;
  default_params: Record<string, unknown>;
}

interface PackRow {
  code: string;
  name: string;
  description?: string;
  subledger_type?: string;
  template_codes: string[];
}

interface DetectorSchema {
  detector_name: string;
  category: string;
  description: string;
  fields: Array<{ name: string; default: unknown; inferred_type: string }>;
}

interface DetectorMeta {
  name: string;
  category: string;
  description: string;
}

export function RunPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const [tab, setTab] = useState<Tab>("template");
  const [datasetId, setDatasetId] = useState<string>(
    () => localStorage.getItem("ts_active_dataset") || "",
  );

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () => api.get<Array<{
      id: string; name: string; record_count: number; subledger_type: string;
    }>>(`/api/datasets${activeProjectId ? `?project_id=${activeProjectId}` : ""}`),
  });

  const activeDataset = datasets.find((d) => d.id === datasetId);

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Run tests" description="Execute templates, packs, or a raw detector." />
        <EmptyState
          icon={<Play className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the top bar."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Run tests"
        description="Execute a single template, a whole pack, or an ad-hoc detector against a dataset."
      />

      <div className="rounded-lg border bg-card p-4 mb-4">
        <Label>Dataset</Label>
        <Select
          value={datasetId}
          onChange={(e) => {
            setDatasetId(e.target.value);
            if (e.target.value) localStorage.setItem("ts_active_dataset", e.target.value);
            else localStorage.removeItem("ts_active_dataset");
          }}
        >
          <option value="">Pick a dataset…</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} — {d.subledger_type.replace(/_/g, " ")} · {d.record_count.toLocaleString()} rows
            </option>
          ))}
        </Select>
        {activeDataset && (
          <div className="text-xs text-muted-foreground mt-2">
            Templates and packs below are scoped to{" "}
            <span className="font-mono">{activeDataset.subledger_type}</span> + universal.
          </div>
        )}
      </div>

      <div className="flex gap-1 border-b mb-4">
        {([
          ["template", "Single template"],
          ["pack", "Pack"],
          ["detector", "Custom detector"],
        ] as Array<[Tab, string]>).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? "border-accent text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "template" && (
        <TemplateTab datasetId={datasetId} subledger={activeDataset?.subledger_type} />
      )}
      {tab === "pack" && (
        <PackTab datasetId={datasetId} subledger={activeDataset?.subledger_type} />
      )}
      {tab === "detector" && <DetectorTab datasetId={datasetId} />}
    </>
  );
}

// ----------- Template tab with searchable picker -----------

function TemplateTab({ datasetId, subledger }: { datasetId: string; subledger?: string }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data: templates = [] } = useQuery({
    queryKey: ["templates", subledger || "all"],
    queryFn: () => {
      const p = new URLSearchParams();
      if (subledger) p.set("subledger", subledger);
      return api.get<TemplateRow[]>(`/api/templates?${p.toString()}`);
    },
  });

  const [search, setSearch] = useState("");
  const [code, setCode] = useState(() => {
    const fromStorage = sessionStorage.getItem("ts_run_template_code");
    if (fromStorage) sessionStorage.removeItem("ts_run_template_code");
    return fromStorage || "";
  });
  const [overrides, setOverrides] = useState("{}");

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return templates.filter(
      (t) =>
        t.code.toLowerCase().includes(q) ||
        t.name.toLowerCase().includes(q) ||
        t.detector_name.toLowerCase().includes(q),
    );
  }, [templates, search]);

  const selected = templates.find((t) => t.code === code);

  const mutation = useMutation({
    mutationFn: () => api.post<TestRun>("/api/runs/template", {
      dataset_id: datasetId,
      template_code: code,
      param_overrides: JSON.parse(overrides || "{}"),
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["all-runs"] });
      toast({
        kind: "success",
        title: `${code} complete`,
        description: `${r.findings_count} finding${r.findings_count === 1 ? "" : "s"}`,
      });
    },
    onError: (e) => toast({ kind: "error", title: "Run failed", description: (e as Error).message }),
  });

  return (
    <SectionCard>
      <div className="space-y-4">
        <div>
          <Label>Search templates</Label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              className="pl-9"
              placeholder="Search by code, name, or detector — e.g. 'weekend', 'AP08', 'benford'"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-2 max-h-[360px] overflow-auto rounded-md border divide-y">
            {filtered.length === 0 ? (
              <div className="p-6 text-sm text-muted-foreground text-center">
                No templates match your search.
              </div>
            ) : (
              filtered.map((t) => (
                <button
                  key={t.code}
                  onClick={() => setCode(t.code)}
                  className={`w-full text-left p-3 hover:bg-secondary transition-colors ${
                    code === t.code ? "bg-accent/10" : ""
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold">{t.code}</span>
                    <span className="text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 bg-muted text-muted-foreground">
                      {t.category}
                    </span>
                    {t.subledger_type && (
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        {t.subledger_type.replace(/_/g, " ")}
                      </span>
                    )}
                  </div>
                  <div className="text-sm mt-1">{t.name}</div>
                  <div className="text-xs text-muted-foreground font-mono">
                    detector: {t.detector_name} · weight {t.default_weight.toFixed(1)}
                  </div>
                </button>
              ))
            )}
          </div>

          <div className="space-y-3">
            <div>
              <Label>Selected</Label>
              <div className="rounded-md border bg-card p-3 min-h-[88px]">
                {selected ? (
                  <>
                    <div className="font-mono text-xs font-semibold">{selected.code}</div>
                    <div className="text-sm mt-0.5">{selected.name}</div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      Detector: {selected.detector_name}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-muted-foreground">Pick a template from the list.</div>
                )}
              </div>
            </div>
            <div>
              <Label>Param overrides (JSON, optional)</Label>
              <textarea
                value={overrides}
                onChange={(e) => setOverrides(e.target.value)}
                className="flex min-h-[80px] w-full rounded-md border border-input bg-card px-3 py-2 font-mono text-xs"
              />
            </div>
            <Button
              onClick={() => mutation.mutate()}
              disabled={!datasetId || !code || mutation.isPending}
              className="w-full"
            >
              <Play className="h-4 w-4" />
              {mutation.isPending ? "Running…" : `Run ${code || "template"}`}
            </Button>
          </div>
        </div>

        {mutation.isSuccess && mutation.data && (
          <div className="rounded-md border border-success/30 bg-success/10 p-3 flex items-center justify-between gap-3">
            <div className="text-sm">
              <span className="font-medium">{mutation.data.findings_count} findings</span>
              <span className="text-muted-foreground"> recorded.</span>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm" variant="outline"
                onClick={() => navigate(`/runs/${(mutation.data as TestRun).id}`)}
              >
                Open this run <ArrowRight className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" variant="accent" onClick={() => navigate("/risk")}>
                Open Risk Explorer <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ----------- Pack tab with picker -----------

function PackTab({ datasetId, subledger }: { datasetId: string; subledger?: string }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [code, setCode] = useState("");

  const { data: packs = [] } = useQuery({
    queryKey: ["packs"],
    queryFn: () => api.get<PackRow[]>("/api/packs"),
  });

  const filtered = useMemo(
    () => packs.filter((p) => !subledger || !p.subledger_type || p.subledger_type === subledger),
    [packs, subledger],
  );

  const selected = packs.find((p) => p.code === code);

  const mutation = useMutation({
    mutationFn: () => api.post<{ pack_run_id: string; summary: { templates_run: number; test_run_ids: string[] } }>(
      "/api/packs/run",
      { dataset_id: datasetId, pack_code: code, template_overrides: {} },
    ),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["all-runs"] });
      toast({
        kind: "success",
        title: `${code} complete`,
        description: `${r.summary.templates_run} templates ran`,
      });
    },
    onError: (e) => toast({ kind: "error", title: "Pack failed", description: (e as Error).message }),
  });

  const ensembleMutation = useMutation({
    mutationFn: async () => {
      const runs = await api.get<TestRun[]>(`/api/datasets/${datasetId}/runs`);
      const completed = runs.filter((r) => r.status === "COMPLETED").map((r) => r.id);
      return api.post<{ summary: { records_scored: number; max_score: number } }>(
        "/api/ensemble", { dataset_id: datasetId, test_run_ids: completed },
      );
    },
    onSuccess: (r) => {
      toast({
        kind: "success",
        title: "Ensemble computed",
        description: `${r.summary.records_scored} records scored (max ${r.summary.max_score.toFixed(1)})`,
      });
    },
    onError: (e) => toast({ kind: "error", title: "Ensemble failed", description: (e as Error).message }),
  });

  return (
    <SectionCard>
      <div className="space-y-4">
        <div>
          <Label>Pack ({filtered.length} available{subledger ? ` for ${subledger.replace(/_/g, " ")}` : ""})</Label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {filtered.map((p) => (
              <button
                key={p.code}
                onClick={() => setCode(p.code)}
                className={`text-left rounded-md border p-3 hover:shadow-sm transition-all ${
                  code === p.code ? "ring-2 ring-accent border-accent" : ""
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold">{p.code}</span>
                  {p.subledger_type && (
                    <span className="text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 bg-muted text-muted-foreground">
                      {p.subledger_type.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
                <div className="text-sm font-medium mt-1">{p.name}</div>
                <div className="text-[11px] text-muted-foreground mt-1">
                  {p.template_codes.length} templates
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            onClick={() => mutation.mutate()}
            disabled={!datasetId || !code || mutation.isPending}
          >
            <Play className="h-4 w-4" />
            {mutation.isPending ? "Running…" : `Run ${code || "pack"}`}
          </Button>
          {selected && (
            <span className="text-xs text-muted-foreground self-center">
              Will run {selected.template_codes.length} templates.
            </span>
          )}
        </div>

        {mutation.isSuccess && mutation.data && (
          <div className="rounded-md border border-success/30 bg-success/10 p-4">
            <div className="text-sm font-medium mb-3">
              ✓ Pack complete: {mutation.data.summary.templates_run} templates ran
            </div>
            <div className="text-xs text-muted-foreground mb-3">
              Next step: compute the ensemble to combine all detector signals into per-record risk scores.
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                size="sm" variant="accent"
                onClick={() => ensembleMutation.mutate()}
                disabled={ensembleMutation.isPending}
              >
                {ensembleMutation.isPending ? "Computing…" : "Compute ensemble"}
              </Button>
              <Button
                size="sm" variant="outline"
                onClick={() => navigate("/runs")}
              >
                Open test runs <ArrowRight className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" variant="outline" onClick={() => navigate("/risk")}>
                Open Risk Explorer <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

// ----------- Detector tab with searchable picker -----------

function DetectorTab({ datasetId }: { datasetId: string }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();

  // List of detectors via templates (no dedicated /api/detectors endpoint exists yet,
  // so we derive a unique set from the templates list).
  const { data: templates = [] } = useQuery({
    queryKey: ["templates", "all"],
    queryFn: () => api.get<TemplateRow[]>("/api/templates"),
  });

  const detectors: DetectorMeta[] = useMemo(() => {
    const seen = new Map<string, DetectorMeta>();
    for (const t of templates) {
      if (!seen.has(t.detector_name)) {
        seen.set(t.detector_name, {
          name: t.detector_name,
          category: t.category,
          description: `Used by ${t.code} — ${t.name}`,
        });
      }
    }
    return Array.from(seen.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [templates]);

  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [schema, setSchema] = useState<DetectorSchema | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return detectors.filter((d) => d.name.toLowerCase().includes(q));
  }, [detectors, search]);

  async function selectDetector(n: string) {
    setName(n);
    try {
      const s = await api.get<DetectorSchema>(`/api/templates/detectors/${n}/schema`);
      setSchema(s);
      const defaults: Record<string, unknown> = {};
      s.fields.forEach((f) => (defaults[f.name] = f.default));
      setValues(defaults);
    } catch (e) {
      toast({ kind: "error", title: "Couldn't load schema", description: (e as Error).message });
    }
  }

  const mutation = useMutation({
    mutationFn: () => api.post<TestRun>("/api/runs/detector", {
      dataset_id: datasetId, detector_name: name, params: values,
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["all-runs"] });
      toast({
        kind: "success",
        title: `${name} complete`,
        description: `${r.findings_count} finding${r.findings_count === 1 ? "" : "s"}`,
      });
    },
    onError: (e) => toast({ kind: "error", title: "Run failed", description: (e as Error).message }),
  });

  return (
    <SectionCard>
      <div className="space-y-4">
        <div>
          <Label>Search detectors ({detectors.length})</Label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              className="pl-9"
              placeholder="benford, weekend, duplicates, isolation_forest…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="max-h-[300px] overflow-auto rounded-md border divide-y">
            {filtered.map((d) => (
              <button
                key={d.name}
                onClick={() => selectDetector(d.name)}
                className={`w-full text-left p-2.5 hover:bg-secondary transition-colors ${
                  name === d.name ? "bg-accent/10" : ""
                }`}
              >
                <div className="font-mono text-xs font-semibold">{d.name}</div>
                <div className="text-[10px] text-muted-foreground">{d.category}</div>
              </button>
            ))}
          </div>

          <div className="lg:col-span-2 space-y-3">
            {!schema ? (
              <div className="text-sm text-muted-foreground py-10 text-center border rounded-md">
                Pick a detector to load its parameters.
              </div>
            ) : (
              <>
                <div className="text-xs text-muted-foreground">
                  <span className="font-mono">{schema.category}</span> — {schema.description}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {schema.fields.map((f) => (
                    <FieldInput
                      key={f.name}
                      field={f}
                      value={values[f.name]}
                      onChange={(v) => setValues({ ...values, [f.name]: v })}
                    />
                  ))}
                </div>
              </>
            )}

            <Button
              onClick={() => mutation.mutate()}
              disabled={!datasetId || !name || mutation.isPending}
              className="w-full"
            >
              <Play className="h-4 w-4" />
              {mutation.isPending ? "Running…" : `Run ${name || "detector"}`}
            </Button>
          </div>
        </div>

        {mutation.isSuccess && mutation.data && (
          <div className="rounded-md border border-success/30 bg-success/10 p-3 flex items-center justify-between gap-3">
            <div className="text-sm">
              <span className="font-medium">{mutation.data.findings_count} findings</span>
              <span className="text-muted-foreground"> recorded.</span>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm" variant="outline"
                onClick={() => navigate(`/runs/${(mutation.data as TestRun).id}`)}
              >
                Open this run <ArrowRight className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" variant="accent" onClick={() => navigate("/risk")}>
                Open Risk Explorer <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function FieldInput({
  field, value, onChange,
}: {
  field: { name: string; inferred_type: string; default: unknown };
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const t = field.inferred_type;
  if (t === "bool") {
    return (
      <div className="col-span-2 flex items-center gap-2">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
        <Label className="mb-0">{field.name}</Label>
      </div>
    );
  }
  if (t === "int" || t === "float") {
    return (
      <div>
        <Label>{field.name}</Label>
        <Input
          type="number"
          value={String(value ?? 0)}
          onChange={(e) => onChange(t === "int" ? parseInt(e.target.value || "0") : parseFloat(e.target.value || "0"))}
        />
      </div>
    );
  }
  if (t === "string_list") {
    return (
      <div className="col-span-2">
        <Label>{field.name} (comma-separated)</Label>
        <Input
          value={Array.isArray(value) ? (value as unknown[]).join(",") : ""}
          onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
        />
      </div>
    );
  }
  if (t === "list" || t === "dict") {
    return (
      <div className="col-span-2">
        <Label>{field.name} (JSON)</Label>
        <textarea
          value={JSON.stringify(value ?? (t === "list" ? [] : {}), null, 2)}
          onChange={(e) => {
            try { onChange(JSON.parse(e.target.value)); } catch { /* partial */ }
          }}
          className="flex min-h-[60px] w-full rounded-md border border-input bg-card px-3 py-2 font-mono text-xs"
        />
      </div>
    );
  }
  return (
    <div>
      <Label>{field.name}</Label>
      <Input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
