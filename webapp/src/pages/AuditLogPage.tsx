import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, ShieldAlert, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, getToken } from "@/lib/api";

interface Envelope {
  chain: { ok: boolean; total_entries: number; broken_at?: string; reason?: string };
  entries: Array<{
    id: string;
    timestamp: string;
    action: string;
    entity_type: string;
    entity_id?: string;
    current_hash: string;
  }>;
}

function entityHref(entityType: string, entityId: string | undefined): string | null {
  if (!entityId) return null;
  switch (entityType) {
    case "finding":
      return `/findings/${entityId}`;
    case "engagement":
      return `/engagements`;
    case "test_run":
      return `/runs/${entityId}`;
    case "dataset":
      return `/datasets`;
    case "schedule":
      return `/schedules`;
    case "monitor":
      return `/monitors`;
    case "user":
      return `/admin`;
    default:
      return null;
  }
}

export function AuditLogPage() {
  const navigate = useNavigate();
  const [actionFilter, setActionFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [search, setSearch] = useState("");
  const { data } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => api.get<Envelope>("/api/audit-log/entries"),
  });

  const allActions = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.entries.map((e) => e.action))).sort();
  }, [data]);
  const allEntities = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.entries.map((e) => e.entity_type))).sort();
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.toLowerCase();
    return data.entries.filter((e) => {
      if (actionFilter && e.action !== actionFilter) return false;
      if (entityFilter && e.entity_type !== entityFilter) return false;
      if (q && !(
        e.action.toLowerCase().includes(q) ||
        e.entity_type.toLowerCase().includes(q) ||
        (e.entity_id || "").toLowerCase().includes(q) ||
        e.current_hash.toLowerCase().includes(q)
      )) return false;
      return true;
    });
  }, [data, actionFilter, entityFilter, search]);

  async function downloadPdf() {
    const r = await fetch("/api/audit-log/pdf",
      { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "audit_log.pdf"; a.click();
  }

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Tamper-evident hash-chained log of every privileged action."
        actions={
          <Button variant="outline" onClick={downloadPdf}>
            <Download className="h-4 w-4" /> Export PDF
          </Button>
        }
      />
      {data && (
        <div
          className={`rounded-lg border p-4 mb-4 flex items-center gap-3 ${
            data.chain.ok ? "border-success/30 bg-success/5" : "border-destructive/30 bg-destructive/5"
          }`}
        >
          {data.chain.ok ? (
            <ShieldCheck className="h-5 w-5 text-success" />
          ) : (
            <ShieldAlert className="h-5 w-5 text-destructive" />
          )}
          <div>
            <div className="font-semibold text-sm">
              {data.chain.ok
                ? `Chain VERIFIED — ${data.chain.total_entries} entries`
                : `Chain BROKEN at ${data.chain.broken_at}`}
            </div>
            {!data.chain.ok && <div className="text-xs text-destructive">{data.chain.reason}</div>}
          </div>
        </div>
      )}
      <SectionCard
        title={`Recent entries (${filtered.length}${data ? ` of ${data.entries.length}` : ""})`}
        actions={
          <div className="flex items-center gap-2">
            <Input placeholder="Search…" value={search}
                   onChange={(e) => setSearch(e.target.value)} className="w-48" />
            <Select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}
                    className="w-44">
              <option value="">All actions</option>
              {allActions.map((a) => <option key={a} value={a}>{a}</option>)}
            </Select>
            <Select value={entityFilter} onChange={(e) => setEntityFilter(e.target.value)}
                    className="w-40">
              <option value="">All entities</option>
              {allEntities.map((e) => <option key={e} value={e}>{e}</option>)}
            </Select>
          </div>
        }
      >
        {!data || data.entries.length === 0 ? (
          <EmptyState
            icon={<CheckCircle2 className="h-5 w-5" />}
            title="No audit entries yet"
            description="Activity will appear here as users interact with the platform."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Timestamp</th>
                  <th className="text-left font-semibold py-2 px-3">Action</th>
                  <th className="text-left font-semibold py-2 px-3">Entity</th>
                  <th className="text-left font-semibold py-2 px-3">ID</th>
                  <th className="text-left font-semibold py-2 px-3">Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {filtered.slice(-300).reverse().map((e) => {
                  const href = entityHref(e.entity_type, e.entity_id);
                  return (
                    <tr
                      key={e.id}
                      className={`hover:bg-secondary/30 ${href ? "cursor-pointer" : ""}`}
                      onClick={() => href && navigate(href)}
                    >
                      <td className="py-2 px-3 text-xs font-mono">
                        {new Date(e.timestamp).toLocaleString()}
                      </td>
                      <td className="py-2 px-3 text-xs font-medium">{e.action}</td>
                      <td className="py-2 px-3 text-xs">{e.entity_type}</td>
                      <td className="py-2 px-3 text-xs font-mono truncate max-w-[160px]">
                        {e.entity_id ? (href ? (
                          <span className="text-accent hover:underline">{e.entity_id.slice(0, 16)}…</span>
                        ) : e.entity_id.slice(0, 16) + "…") : "—"}
                      </td>
                      <td className="py-2 px-3 text-xs font-mono text-muted-foreground">
                        {e.current_hash.slice(0, 12)}…
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </>
  );
}
