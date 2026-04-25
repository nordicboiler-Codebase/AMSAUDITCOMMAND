import { useQuery } from "@tanstack/react-query";
import { Package, Play, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

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
    </>
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
