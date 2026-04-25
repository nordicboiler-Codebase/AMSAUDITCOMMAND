import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Package, Play, Search, Sparkles, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AiStatusBadge, useAiStatus } from "@/components/ui/ai-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface Template {
  code: string;
  name: string;
  description?: string;
  detector_name: string;
  category: string;
  default_weight: number;
  subledger_type?: string;
  tags: string[];
  default_params: Record<string, unknown>;
}

const SUBLEDGERS = [
  "", "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "GENERAL_LEDGER", "PAYROLL",
  "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES",
];

const CATEGORIES = ["", "DATA_QUALITY", "FRAUD", "COMPLIANCE", "ANALYTICAL"];

export function TemplatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const codeParam = searchParams.get("code") || "";
  const [subledger, setSubledger] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState(codeParam);
  const [selected, setSelected] = useState<Template | null>(null);
  const [genOpen, setGenOpen] = useState(false);

  const { data: all = [] } = useQuery({
    queryKey: ["templates", subledger],
    queryFn: () => {
      const p = new URLSearchParams();
      if (subledger) p.set("subledger", subledger);
      return api.get<Template[]>(`/api/templates?${p.toString()}`);
    },
  });

  // Auto-select template specified in ?code= once data is available.
  useEffect(() => {
    if (codeParam && all.length && !selected) {
      const match = all.find((t) => t.code === codeParam);
      if (match) setSelected(match);
    }
  }, [codeParam, all, selected]);

  const templates = useMemo(() => {
    return all.filter((t) => {
      if (category && t.category !== category) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          t.code.toLowerCase().includes(q) ||
          t.name.toLowerCase().includes(q) ||
          t.detector_name.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [all, category, search]);

  return (
    <>
      <PageHeader
        title="Templates"
        description="148 named audit tests bound to 36 reusable detectors. Filter or search."
        actions={
          <div className="flex items-center gap-2">
            <AiStatusBadge />
            <Button onClick={() => setGenOpen(true)}>
              <Sparkles className="h-4 w-4 text-accent" /> Create from description
            </Button>
          </div>
        }
      />

      <div className="rounded-lg border bg-card p-4 mb-4 flex gap-3 items-end flex-wrap">
        <div className="flex-1 min-w-[240px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search by code, name, or detector…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div>
          <Select value={subledger} onChange={(e) => setSubledger(e.target.value)} className="w-[180px]">
            {SUBLEDGERS.map((s) => (
              <option key={s || "all"} value={s}>{s ? s.replace(/_/g, " ") : "All subledgers"}</option>
            ))}
          </Select>
        </div>
        <div>
          <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-[160px]">
            {CATEGORIES.map((c) => (
              <option key={c || "all"} value={c}>{c || "All categories"}</option>
            ))}
          </Select>
        </div>
        <div className="text-sm text-muted-foreground">{templates.length} shown</div>
      </div>

      {templates.length === 0 ? (
        <EmptyState
          icon={<Package className="h-5 w-5" />}
          title="No templates match"
          description="Try relaxing the filters or clearing the search."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SectionCard className="lg:col-span-2" title={`${templates.length} templates`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left font-semibold py-2 px-3">Code</th>
                    <th className="text-left font-semibold py-2 px-3">Name</th>
                    <th className="text-left font-semibold py-2 px-3">Detector</th>
                    <th className="text-left font-semibold py-2 px-3">Category</th>
                    <th className="text-right font-semibold py-2 px-3">Weight</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {templates.map((t) => (
                    <tr
                      key={t.code}
                      onClick={() => setSelected(t)}
                      className={`cursor-pointer hover:bg-secondary/30 ${
                        selected?.code === t.code ? "bg-secondary/50" : ""
                      }`}
                    >
                      <td className="py-2 px-3 font-mono text-xs font-medium">{t.code}</td>
                      <td className="py-2 px-3">{t.name}</td>
                      <td className="py-2 px-3 font-mono text-xs text-muted-foreground">
                        {t.detector_name}
                      </td>
                      <td className="py-2 px-3"><Badge tone="muted">{t.category}</Badge></td>
                      <td className="py-2 px-3 text-right tabular-nums">{t.default_weight.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
          <SectionCard title={selected ? `${selected.code}` : "Detail"}>
            {!selected ? (
              <div className="text-sm text-muted-foreground py-10 text-center">
                Select a template to see its params.
              </div>
            ) : (
              <>
                <div className="text-base font-semibold">{selected.name}</div>
                <div className="text-xs text-muted-foreground mt-1">{selected.description}</div>
                <Button
                  variant="accent" size="sm" className="w-full mt-3"
                  onClick={() => {
                    sessionStorage.setItem("ts_run_template_code", selected.code);
                    navigate("/run");
                  }}
                >
                  <Play className="h-4 w-4" /> Run this template
                </Button>
                <button
                  onClick={() => navigate(`/runs?template=${encodeURIComponent(selected.code)}`)}
                  className="w-full mt-2 text-xs text-accent hover:underline text-center"
                >
                  View past runs of this template →
                </button>
                <div className="mt-4 space-y-2 text-xs">
                  <InfoRow label="Detector" value={selected.detector_name} mono />
                  <InfoRow label="Category" value={selected.category} />
                  <InfoRow label="Weight" value={selected.default_weight.toFixed(2)} />
                  {selected.subledger_type && (
                    <InfoRow label="Subledger" value={selected.subledger_type.replace(/_/g, " ")} />
                  )}
                </div>
                <div className="mt-4">
                  <div className="eyebrow mb-2">Default params</div>
                  <pre className="bg-secondary rounded-md p-3 text-[11px] overflow-auto max-h-[240px]">
                    {JSON.stringify(selected.default_params, null, 2)}
                  </pre>
                </div>
              </>
            )}
          </SectionCard>
        </div>
      )}

      {genOpen && (
        <GenerateFromDescriptionDialog
          onClose={() => setGenOpen(false)}
          onCreated={(code) => {
            setGenOpen(false);
            // Move the search box to the new code so it pops to the top.
            setSearch(code);
          }}
        />
      )}
    </>
  );
}

interface TemplateProposal {
  code?: string;
  name?: string;
  description?: string;
  detector_name?: string | null;
  default_params?: Record<string, unknown>;
  category?: string;
  subledger?: string | null;
  default_weight?: number;
  tags?: string[];
  rationale?: string;
  validation_warnings?: string[];
  error?: string;
  raw?: string;
}

function GenerateFromDescriptionDialog({
  onClose, onCreated,
}: {
  onClose: () => void;
  onCreated: (code: string) => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: aiStatus } = useAiStatus();
  const providerName =
    aiStatus?.providers?.find((p) => p.provider === aiStatus.active)?.label?.split(" (")[0] || "AI";

  const [description, setDescription] = useState("");
  const [proposal, setProposal] = useState<TemplateProposal | null>(null);
  // Editable fields when proposal arrives:
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [detector, setDetector] = useState("");
  const [paramsJson, setParamsJson] = useState("{}");
  const [category, setCategory] = useState("ANALYTICAL");
  const [subledger, setSubledger] = useState<string>("");
  const [weight, setWeight] = useState(5);
  const [tags, setTags] = useState("");

  const generate = useMutation({
    mutationFn: () =>
      api.post<TemplateProposal>("/api/templates/from-description", { description }),
    onSuccess: (p) => {
      setProposal(p);
      if (p.error || !p.detector_name) return;
      setCode(p.code || "");
      setName(p.name || "");
      setDesc(p.description || "");
      setDetector(p.detector_name || "");
      setParamsJson(JSON.stringify(p.default_params ?? {}, null, 2));
      setCategory(p.category || "ANALYTICAL");
      setSubledger(p.subledger || "");
      setWeight(p.default_weight ?? 5);
      setTags((p.tags || []).join(", "));
    },
    onError: (e) => toast({ kind: "error", title: "Generation failed", description: (e as Error).message }),
  });

  const save = useMutation({
    mutationFn: () => {
      let params: Record<string, unknown> = {};
      try { params = JSON.parse(paramsJson || "{}"); } catch (_) { /* validated below */ }
      return api.post<{ code: string }>("/api/templates", {
        code, name, description: desc, detector_name: detector,
        default_params: params,
        category,
        subledger: subledger || null,
        default_weight: Number(weight),
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["templates"] });
      toast({ kind: "success", title: `Template ${created.code} created` });
      onCreated(created.code);
    },
    onError: (e) => toast({ kind: "error", title: "Save failed", description: (e as Error).message }),
  });

  let paramsValid = true;
  try { JSON.parse(paramsJson || "{}"); } catch { paramsValid = false; }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50 overflow-auto">
      <div className="w-full max-w-2xl rounded-lg bg-card border shadow-lg my-8 max-h-[90vh] flex flex-col">
        <div className="p-5 border-b flex items-start gap-3">
          <Sparkles className="h-5 w-5 text-accent shrink-0 mt-0.5" />
          <div>
            <h3 className="text-base font-semibold">Create template from description</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {providerName} picks the right detector and fills in the params. You review and save.
              Templates always bind to an existing detector — never new code.
            </p>
          </div>
        </div>

        <div className="p-5 space-y-4 overflow-auto flex-1">
          <div>
            <Label>Describe the test you want</Label>
            <Textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. flag accounts payable invoices entered on weekends with round amounts above $50,000 to vendors created in the last 30 days"
              autoFocus
            />
            <div className="mt-2 flex justify-end">
              <Button
                onClick={() => generate.mutate()}
                disabled={!description.trim() || generate.isPending}
              >
                <Sparkles className="h-4 w-4" />
                {generate.isPending ? "Generating…" : proposal ? "Re-generate" : "Generate proposal"}
              </Button>
            </div>
          </div>

          {proposal?.error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {proposal.error}
              {proposal.raw && (
                <pre className="text-[11px] font-mono mt-2 max-h-40 overflow-auto">{proposal.raw}</pre>
              )}
            </div>
          )}

          {proposal && !proposal.error && proposal.detector_name && (
            <>
              <div className="rounded-md border border-accent/30 bg-accent/5 p-3 text-xs">
                <div className="font-semibold mb-1 flex items-center gap-1.5">
                  <Wand2 className="h-3.5 w-3.5 text-accent" /> {providerName}'s rationale
                </div>
                <div className="text-muted-foreground whitespace-pre-wrap">
                  {proposal.rationale}
                </div>
                {proposal.validation_warnings && proposal.validation_warnings.length > 0 && (
                  <div className="mt-2 text-warning">
                    {proposal.validation_warnings.map((w, i) => (<div key={i}>⚠ {w}</div>))}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Code</Label>
                  <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} className="font-mono" />
                </div>
                <div>
                  <Label>Detector (read-only)</Label>
                  <Input value={detector} readOnly className="font-mono opacity-70" />
                </div>
                <div className="col-span-2">
                  <Label>Name</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="col-span-2">
                  <Label>Description</Label>
                  <Textarea rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} />
                </div>
                <div>
                  <Label>Category</Label>
                  <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                    {["DATA_QUALITY", "FRAUD", "COMPLIANCE", "ANALYTICAL"].map((c) =>
                      <option key={c} value={c}>{c}</option>
                    )}
                  </Select>
                </div>
                <div>
                  <Label>Subledger</Label>
                  <Select value={subledger} onChange={(e) => setSubledger(e.target.value)}>
                    <option value="">Universal</option>
                    {["GENERAL_LEDGER", "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "PAYROLL",
                      "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
                    ].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                  </Select>
                </div>
                <div>
                  <Label>Default weight (1-10)</Label>
                  <Input
                    type="number" min={1} max={10} step={0.5}
                    value={weight}
                    onChange={(e) => setWeight(Number(e.target.value))}
                  />
                </div>
                <div>
                  <Label>Tags (comma-separated)</Label>
                  <Input value={tags} onChange={(e) => setTags(e.target.value)} />
                </div>
                <div className="col-span-2">
                  <Label>Default params (JSON)</Label>
                  <textarea
                    rows={6}
                    value={paramsJson}
                    onChange={(e) => setParamsJson(e.target.value)}
                    className={`flex w-full rounded-md border px-3 py-2 font-mono text-xs bg-card ${
                      paramsValid ? "border-input" : "border-destructive"
                    }`}
                  />
                  {!paramsValid && (
                    <div className="text-[11px] text-destructive mt-1">Invalid JSON.</div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="p-4 border-t flex justify-end gap-2 bg-card">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => save.mutate()}
            disabled={!proposal || !!proposal.error || !code || !name || !detector || !paramsValid || save.isPending}
          >
            {save.isPending ? "Saving…" : "Save template"}
          </Button>
        </div>
      </div>
    </div>
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
