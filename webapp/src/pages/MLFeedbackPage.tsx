import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { EmptyState, MetricCard, PageHeader, SectionCard } from "@/components/ui/page";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/utils";

interface PrecisionRow {
  name: string;
  true_positive: number;
  false_positive: number;
  precision: number;
  suggested_weight_scale: number;
}
interface Report {
  summary: { total_labels: number; true_positive: number; false_positive: number; overall_precision: number };
  per_detector: PrecisionRow[];
  per_template: PrecisionRow[];
}

export function MLFeedbackPage() {
  const { data } = useQuery({
    queryKey: ["feedback"],
    queryFn: () => api.get<Report>("/api/feedback/precision"),
  });
  if (!data) return null;
  const s = data.summary;

  return (
    <>
      <PageHeader
        title="ML Feedback"
        description="Precision per detector, learned from closed findings (CONFIRMED → true positive, FALSE_POSITIVE → false positive)."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard label="Total labels" value={s.total_labels} />
        <MetricCard label="True positives" value={s.true_positive} accent="hsl(146 72% 29%)" />
        <MetricCard label="False positives" value={s.false_positive} accent="hsl(0 70% 50%)" />
        <MetricCard label="Overall precision" value={formatPercent(s.overall_precision)} accent="hsl(175 82% 42%)" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PrecisionTable title="Per detector" rows={data.per_detector} />
        <PrecisionTable title="Per template" rows={data.per_template} />
      </div>
    </>
  );
}

function PrecisionTable({ title, rows }: { title: string; rows: PrecisionRow[] }) {
  if (!rows.length) {
    return (
      <SectionCard title={title}>
        <EmptyState
          icon={<Sparkles className="h-5 w-5" />}
          title="No labels yet"
          description="Close findings as CONFIRMED or FALSE_POSITIVE to train the model."
        />
      </SectionCard>
    );
  }
  return (
    <SectionCard title={title}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left font-semibold py-2 px-3">Name</th>
              <th className="text-right font-semibold py-2 px-3">TP</th>
              <th className="text-right font-semibold py-2 px-3">FP</th>
              <th className="text-right font-semibold py-2 px-3">Precision</th>
              <th className="text-right font-semibold py-2 px-3">Suggest × weight</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => {
              const prec = r.precision;
              const color =
                prec >= 0.8 ? "text-success" : prec >= 0.5 ? "text-warning" : "text-destructive";
              return (
                <tr key={r.name} className="hover:bg-secondary/30">
                  <td className="py-2 px-3 font-medium">{r.name}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{r.true_positive}</td>
                  <td className="py-2 px-3 text-right tabular-nums">{r.false_positive}</td>
                  <td className={`py-2 px-3 text-right tabular-nums font-semibold ${color}`}>
                    {formatPercent(prec)}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums text-muted-foreground">
                    ×{r.suggested_weight_scale.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
