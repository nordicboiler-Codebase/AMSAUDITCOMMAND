import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { api } from "@/lib/api";

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

export function AuditLogPage() {
  const { data } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => api.get<Envelope>("/api/audit-log/entries"),
  });

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Tamper-evident hash-chained log of every privileged action."
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
      <SectionCard title="Recent entries">
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
                {data.entries.slice(-200).reverse().map((e) => (
                  <tr key={e.id} className="hover:bg-secondary/30">
                    <td className="py-2 px-3 text-xs font-mono">
                      {new Date(e.timestamp).toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-xs font-medium">{e.action}</td>
                    <td className="py-2 px-3 text-xs">{e.entity_type}</td>
                    <td className="py-2 px-3 text-xs font-mono truncate max-w-[160px]">
                      {e.entity_id || "—"}
                    </td>
                    <td className="py-2 px-3 text-xs font-mono text-muted-foreground">
                      {e.current_hash.slice(0, 12)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </>
  );
}
