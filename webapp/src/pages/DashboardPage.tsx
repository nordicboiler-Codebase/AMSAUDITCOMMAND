import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, Building2, Clock, Database, FileSearch, FolderKanban,
  Package, Play,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useNavigate } from "react-router-dom";
import { EmptyState, MetricCard, PageHeader, SectionCard } from "@/components/ui/page";
import { api, type DashboardMetrics, type SubsidiaryRollup } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

function severityColor(score: number) {
  if (score >= 90) return "#821b1a";
  if (score >= 70) return "#c2342f";
  if (score >= 40) return "#b76e00";
  return "#0f766e";
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: metrics } = useQuery({
    queryKey: ["metrics"],
    queryFn: () => api.get<DashboardMetrics>("/api/metrics/dashboard"),
  });
  const { data: rollup = [] } = useQuery({
    queryKey: ["rollup"],
    queryFn: () => api.get<SubsidiaryRollup[]>("/api/subsidiaries/rollup"),
  });

  if (!metrics) return null;

  const trend = metrics.finding_trend_last_84d.map((t) => ({
    week: new Date(t.week).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    count: t.count,
  }));
  const severity = Object.entries(metrics.findings_by_severity).map(([s, n]) => ({ severity: s, count: n }));

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Group-wide audit posture across subsidiaries, engagements, and open findings."
      />

      {/* Gradient group banner */}
      <div className="rounded-lg bg-gradient-to-r from-primary to-[#0f4a5a] text-white p-5 mb-6 flex items-center gap-5 shadow-sm">
        <div className="h-12 w-12 rounded-md bg-white/10 flex items-center justify-center">
          <Building2 className="h-6 w-6" />
        </div>
        <div>
          <div className="font-semibold text-base">
            Group audit — {rollup.length} subsidiar{rollup.length === 1 ? "y" : "ies"} in scope
          </div>
          <div className="text-sm text-white/75 mt-0.5">
            {rollup.reduce((s, r) => s + r.findings_open, 0)} open findings ·{" "}
            {rollup.reduce((s, r) => s + r.findings_high_critical, 0)} high/critical ·{" "}
            {rollup.reduce((s, r) => s + r.test_runs, 0)} test runs logged
          </div>
        </div>
      </div>

      {/* Metric grid — every tile is a deep link */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <button onClick={() => navigate("/findings?status=DRAFT,UNDER_REVIEW,CONFIRMED")}
                className="text-left">
          <MetricCard
            label="Open findings" value={formatNumber(metrics.findings_open)}
            icon={<FileSearch className="h-5 w-5" />}
            hint={`+${metrics.findings_this_month} last 30d`}
            trend={metrics.findings_this_month > 0 ? "up" : "flat"}
          />
        </button>
        <button onClick={() => navigate("/findings?severity=HIGH,CRITICAL")} className="text-left">
          <MetricCard
            label="High / Critical" value={formatNumber(metrics.findings_high_or_critical)}
            icon={<AlertTriangle className="h-5 w-5" />}
            accent={metrics.findings_high_or_critical ? "hsl(0 70% 50%)" : undefined}
          />
        </button>
        <button onClick={() => navigate("/engagements")} className="text-left">
          <MetricCard
            label="Active engagements" value={formatNumber(metrics.engagements_in_progress)}
            icon={<FolderKanban className="h-5 w-5" />}
          />
        </button>
        <button onClick={() => navigate("/subsidiaries")} className="text-left">
          <MetricCard
            label="Subsidiaries" value={formatNumber(rollup.length)}
            icon={<Building2 className="h-5 w-5" />}
          />
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <button onClick={() => navigate("/runs")} className="text-left">
          <MetricCard label="Runs last 7 days" value={formatNumber(metrics.runs_this_week)}
                      icon={<Play className="h-5 w-5" />} />
        </button>
        <button onClick={() => navigate("/schedules")} className="text-left">
          <MetricCard label="Active schedules" value={formatNumber(metrics.schedules_active)}
                      icon={<Clock className="h-5 w-5" />} />
        </button>
        <button onClick={() => navigate("/datasets")} className="text-left">
          <MetricCard label="Datasets imported" value={formatNumber(metrics.datasets)}
                      icon={<Database className="h-5 w-5" />} />
        </button>
        <button onClick={() => navigate("/templates")} className="text-left">
          <MetricCard label="Named tests" value="148"
                      icon={<Package className="h-5 w-5" />} />
        </button>
      </div>

      {/* Two-column: heatmap + trend */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
        <SectionCard title="Subsidiary risk heatmap" className="lg:col-span-2">
          {rollup.length === 0 ? (
            <EmptyState
              icon={<Building2 className="h-5 w-5" />}
              title="No subsidiaries configured"
              description="Register group entities in the Subsidiaries page."
            />
          ) : (
            <div className="space-y-2">
              {rollup.slice(0, 8).map((r) => {
                const color = severityColor(r.max_risk_score);
                return (
                  <button
                    key={r.code}
                    onClick={() => navigate(`/findings?subsidiary=${r.code}`)}
                    className="w-full text-left rounded-md border bg-card p-3 flex items-center justify-between hover:shadow-sm transition-shadow"
                    style={{ borderLeft: `3px solid ${color}` }}
                  >
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                        {r.code}
                      </div>
                      <div className="text-sm font-medium truncate">{r.name}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {r.findings_open} open · {r.findings_high_critical} H/C · {r.test_runs} runs
                      </div>
                    </div>
                    <div className="text-xl font-bold tabular-nums" style={{ color }}>
                      {r.max_risk_score.toFixed(0)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Findings trend — last 12 weeks" className="lg:col-span-3">
          {trend.length === 0 ? (
            <EmptyState
              icon={<FileSearch className="h-5 w-5" />}
              title="No historical data yet"
              description="Trend populates once findings accumulate over multiple weeks."
            />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="week" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))", border: "1px solid hsl(var(--border))",
                    borderRadius: "8px", fontSize: "12px",
                  }}
                />
                <Line type="monotone" dataKey="count" stroke="hsl(var(--accent))" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </SectionCard>
      </div>

      {/* Severity mix */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
        <SectionCard title="Severity mix (open findings)" className="lg:col-span-2">
          {severity.length === 0 ? (
            <EmptyState
              icon={<FileSearch className="h-5 w-5" />}
              title="No open findings"
              description="You're clear across all subsidiaries."
            />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={severity}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="severity" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))", border: "1px solid hsl(var(--border))",
                    borderRadius: "8px", fontSize: "12px",
                  }}
                />
                <Bar dataKey="count" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        <SectionCard title="Top 10 records at risk — cross-subsidiary" className="lg:col-span-3">
          {metrics.top_risk_records.length === 0 ? (
            <EmptyState
              icon={<FileSearch className="h-5 w-5" />}
              title="No risk scores yet"
              description="Run a pack and compute an ensemble to see the top-risk roll-up."
            />
          ) : (
            <div className="divide-y">
              {metrics.top_risk_records.map((r) => (
                <button
                  key={r.record_key}
                  onClick={() => navigate(`/risk?record=${encodeURIComponent(r.record_key)}`)}
                  className="w-full flex items-center justify-between py-2.5 px-2 -mx-2 hover:bg-secondary/30 rounded text-left"
                >
                  <div className="min-w-0">
                    <div className="font-mono text-sm font-medium truncate">{r.record_key}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {r.detectors.join(" · ")}
                    </div>
                  </div>
                  <div
                    className="text-base font-bold tabular-nums shrink-0"
                    style={{ color: severityColor(r.score) }}
                  >
                    {r.score.toFixed(1)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </SectionCard>
      </div>
    </>
  );
}
