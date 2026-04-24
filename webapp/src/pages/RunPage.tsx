import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, type TestRun } from "@/lib/api";

type Tab = "template" | "pack" | "detector";

interface DetectorSchema {
  detector_name: string;
  category: string;
  description: string;
  fields: Array<{ name: string; default: unknown; inferred_type: string }>;
}

export function RunPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const [tab, setTab] = useState<Tab>("template");
  const [datasetId, setDatasetId] = useState<string>(
    () => localStorage.getItem("ts_active_dataset") || "",
  );

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () => api.get<Array<{ id: string; name: string; record_count: number }>>(
      `/api/datasets${activeProjectId ? `?project_id=${activeProjectId}` : ""}`,
    ),
  });

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Run tests" description="Execute templates, packs, or a raw detector." />
        <EmptyState
          icon={<Play className="h-5 w-5" />}
          title="No active project"
          description="Pick a project in the sidebar."
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
            localStorage.setItem("ts_active_dataset", e.target.value);
          }}
        >
          <option value="">Pick a dataset…</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({d.record_count.toLocaleString()} rows)
            </option>
          ))}
        </Select>
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
              tab === t
                ? "border-accent text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "template" && <TemplateTab datasetId={datasetId} />}
      {tab === "pack" && <PackTab datasetId={datasetId} />}
      {tab === "detector" && <DetectorTab datasetId={datasetId} />}
    </>
  );
}

function TemplateTab({ datasetId }: { datasetId: string }) {
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [override, setOverride] = useState("{}");
  const mutation = useMutation({
    mutationFn: () => api.post<TestRun>("/api/runs/template", {
      dataset_id: datasetId,
      template_code: code,
      param_overrides: JSON.parse(override || "{}"),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });

  return (
    <SectionCard>
      <div className="space-y-4">
        <div>
          <Label>Template code</Label>
          <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
                 placeholder="e.g. AP08" />
        </div>
        <div>
          <Label>Param overrides (JSON)</Label>
          <textarea
            value={override} onChange={(e) => setOverride(e.target.value)}
            className="flex min-h-[100px] w-full rounded-md border border-input bg-card px-3 py-2 font-mono text-xs"
          />
        </div>
        <Button
          onClick={() => mutation.mutate()}
          disabled={!datasetId || !code || mutation.isPending}
        >
          <Play className="h-4 w-4" />
          {mutation.isPending ? "Running…" : "Run template"}
        </Button>
        {renderResult(mutation)}
      </div>
    </SectionCard>
  );
}

function PackTab({ datasetId }: { datasetId: string }) {
  const qc = useQueryClient();
  const [pack, setPack] = useState("AP_STANDARD");
  const mutation = useMutation({
    mutationFn: () => api.post("/api/packs/run", {
      dataset_id: datasetId, pack_code: pack, template_overrides: {},
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
  return (
    <SectionCard>
      <div className="space-y-4">
        <div>
          <Label>Pack code</Label>
          <Input value={pack} onChange={(e) => setPack(e.target.value.toUpperCase())} />
        </div>
        <Button onClick={() => mutation.mutate()} disabled={!datasetId || mutation.isPending}>
          <Play className="h-4 w-4" />
          {mutation.isPending ? "Running pack…" : "Run pack"}
        </Button>
        {renderResult(mutation)}
      </div>
    </SectionCard>
  );
}

function DetectorTab({ datasetId }: { datasetId: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [schema, setSchema] = useState<DetectorSchema | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});

  async function loadSchema() {
    if (!name) return;
    try {
      const s = await api.get<DetectorSchema>(`/api/templates/detectors/${name}/schema`);
      setSchema(s);
      const defaults: Record<string, unknown> = {};
      s.fields.forEach((f) => (defaults[f.name] = f.default));
      setValues(defaults);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  const mutation = useMutation({
    mutationFn: () => api.post<TestRun>("/api/runs/detector", {
      dataset_id: datasetId, detector_name: name, params: values,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });

  return (
    <SectionCard>
      <div className="space-y-4">
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <Label>Detector name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)}
                   placeholder="e.g. benford, duplicates, weekend_transactions" />
          </div>
          <Button variant="outline" onClick={loadSchema}>Load params</Button>
        </div>

        {schema && (
          <>
            <div className="text-xs text-muted-foreground">
              <span className="font-mono">{schema.category}</span> — {schema.description}
            </div>
            <div className="space-y-3">
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
        >
          <Play className="h-4 w-4" />
          {mutation.isPending ? "Running…" : "Run detector"}
        </Button>
        {renderResult(mutation)}
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
      <div className="flex items-center gap-2">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
        <Label>{field.name}</Label>
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
      <div>
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
      <div>
        <Label>{field.name} (JSON)</Label>
        <textarea
          value={JSON.stringify(value ?? (t === "list" ? [] : {}), null, 2)}
          onChange={(e) => {
            try { onChange(JSON.parse(e.target.value)); } catch { /* partial */ }
          }}
          className="flex min-h-[70px] w-full rounded-md border border-input bg-card px-3 py-2 font-mono text-xs"
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

function renderResult(m: { isSuccess: boolean; isError: boolean; data: unknown; error: unknown }) {
  if (m.isSuccess && m.data) {
    const d = m.data as { findings_count?: number; summary?: { templates_run?: number } };
    return (
      <div className="rounded-md border border-success/30 bg-success/10 p-3 text-sm">
        <div className="font-medium">Complete</div>
        <div className="text-xs text-muted-foreground mt-1">
          {d.findings_count !== undefined ? `${d.findings_count} findings` : ""}
          {d.summary?.templates_run ? `${d.summary.templates_run} templates ran` : ""}
        </div>
      </div>
    );
  }
  if (m.isError) {
    return <div className="text-sm text-destructive">{(m.error as Error).message}</div>;
  }
  return null;
}
