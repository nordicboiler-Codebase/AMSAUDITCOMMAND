import { useMutation, useQuery } from "@tanstack/react-query";
import { Cable, Download } from "lucide-react";
import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface ConnectorSchemaField {
  type?: string;
  required?: boolean;
  default?: unknown;
  secret?: boolean;
  description?: string;
  choices?: string[];
}

interface ConnectorMeta {
  name: string;
  description: string;
  config_schema: Record<string, ConnectorSchemaField>;
}

const SUBLEDGERS = [
  "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "GENERAL_LEDGER", "PAYROLL",
  "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
];

export function ConnectorsPage() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const { toast } = useToast();

  const { data: connectors = [] } = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api.get<ConnectorMeta[]>("/api/connectors"),
  });

  const [selected, setSelected] = useState<string>("");
  const [datasetName, setDatasetName] = useState("");
  const [subledger, setSubledger] = useState("ACCOUNTS_PAYABLE");
  const [config, setConfig] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!selected && connectors.length > 0) setSelected(connectors[0].name);
  }, [connectors, selected]);

  useEffect(() => {
    const meta = connectors.find((c) => c.name === selected);
    if (!meta) return;
    const initial: Record<string, unknown> = {};
    Object.entries(meta.config_schema).forEach(([k, f]) => {
      if (f.default !== undefined) initial[k] = f.default;
    });
    setConfig(initial);
  }, [selected, connectors]);

  const meta = connectors.find((c) => c.name === selected);
  const mutation = useMutation({
    mutationFn: () => api.post<{ dataset_id: string; record_count: number; rows_pulled: number }>(
      "/api/connectors/pull-and-import",
      {
        connector: selected,
        project_id: activeProjectId,
        dataset_name: datasetName,
        subledger_type: subledger,
        config,
      },
    ),
    onSuccess: (d) => {
      toast({
        kind: "success",
        title: "Pulled and imported",
        description: `${d.rows_pulled ?? d.record_count} rows · dataset ${d.dataset_id.slice(0, 8)}…`,
      });
    },
    onError: (e) => toast({ kind: "error", title: "Pull failed", description: (e as Error).message }),
  });

  if (!activeProjectId) {
    return (
      <>
        <PageHeader title="Connectors" description="Pull data from SAP S/4, Oracle Fusion, or SFTP." />
        <EmptyState icon={<Cable className="h-5 w-5" />} title="No active project"
                    description="Connectors stage data into the active project." />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Connectors"
        description="Pull data from your ERP / SFTP, hash + import as a dataset in one step."
      />

      {connectors.length === 0 ? (
        <EmptyState icon={<Cable className="h-5 w-5" />} title="No connectors registered" description="" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-1 space-y-2">
            <div className="eyebrow mb-2">Available connectors</div>
            {connectors.map((c) => (
              <button
                key={c.name}
                onClick={() => setSelected(c.name)}
                className={`w-full text-left rounded-lg border bg-card p-4 transition-all hover:shadow-sm ${
                  selected === c.name ? "ring-2 ring-accent border-accent" : ""
                }`}
              >
                <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                  {c.name}
                </div>
                <div className="text-sm font-medium mt-1">{c.description}</div>
              </button>
            ))}
          </div>

          <div className="lg:col-span-2">
            {meta ? (
              <SectionCard title={`${meta.name} — pull and import`}>
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div>
                    <Label>Dataset name (new)</Label>
                    <Input
                      value={datasetName}
                      onChange={(e) => setDatasetName(e.target.value)}
                      placeholder="AP March 2026 (SAP)"
                    />
                  </div>
                  <div>
                    <Label>Subledger</Label>
                    <Select value={subledger} onChange={(e) => setSubledger(e.target.value)}>
                      {SUBLEDGERS.map((s) => (
                        <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                      ))}
                    </Select>
                  </div>
                </div>

                <div className="eyebrow mb-3">Connector config</div>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(meta.config_schema).map(([key, field]) => (
                    <div key={key} className={field.type === "string" || field.secret ? "" : "col-span-2"}>
                      <Label>
                        {key}
                        {field.required ? <span className="text-destructive ml-1">*</span> : null}
                      </Label>
                      {field.choices ? (
                        <Select
                          value={String(config[key] ?? field.default ?? "")}
                          onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
                        >
                          {field.choices.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </Select>
                      ) : field.type === "int" ? (
                        <Input
                          type="number"
                          value={Number(config[key] ?? field.default ?? 0)}
                          onChange={(e) => setConfig({ ...config, [key]: Number(e.target.value) })}
                        />
                      ) : (
                        <Input
                          type={field.secret ? "password" : "text"}
                          value={String(config[key] ?? "")}
                          onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
                          placeholder={field.description}
                        />
                      )}
                      {field.description && (
                        <div className="text-[11px] text-muted-foreground mt-1">{field.description}</div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="mt-5 pt-4 border-t flex justify-end">
                  <Button
                    onClick={() => mutation.mutate()}
                    disabled={!datasetName || mutation.isPending}
                  >
                    <Download className="h-4 w-4" />
                    {mutation.isPending ? "Pulling…" : "Pull from source and import"}
                  </Button>
                </div>
              </SectionCard>
            ) : null}
          </div>
        </div>
      )}
    </>
  );
}
