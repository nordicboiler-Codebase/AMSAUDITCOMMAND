import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Download, FileSearch, Target } from "lucide-react";
import { useOutletContext } from "react-router-dom";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, getToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";

type Tab = "sso" | "email" | "mfa" | "retention" | "siem" | "bi";

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("sso");
  return (
    <>
      <PageHeader title="Settings" description="Platform configuration — SSO, email, MFA, retention, SIEM, BI feeds." />
      <div className="flex gap-1 border-b mb-5 flex-wrap">
        {([
          ["sso", "SSO"], ["email", "Email"], ["mfa", "My MFA"],
          ["retention", "Data retention"], ["siem", "SIEM webhook"],
          ["bi", "BI feeds"],
        ] as Array<[Tab, string]>).map(([k, label]) => (
          <button
            key={k} onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === k ? "border-accent text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "sso" && <SsoTab />}
      {tab === "email" && <EmailTab />}
      {tab === "mfa" && <MfaTab />}
      {tab === "retention" && <RetentionTab />}
      {tab === "siem" && <SiemTab />}
      {tab === "bi" && <BiTab />}
    </>
  );
}

function BiTab() {
  const { activeProjectId } = useOutletContext<{ activeProjectId: string | null }>();
  const { toast } = useToast();
  const { data: manifest } = useQuery({
    queryKey: ["bi-manifest"],
    queryFn: () => api.get<{ feeds: Array<{ name: string; url: string; format: string }> }>(
      "/api/bi/manifest.json",
    ),
  });

  async function downloadFeed(url: string, name: string) {
    try {
      const fullUrl = activeProjectId ? `${url}?project_id=${activeProjectId}` : url;
      const r = await fetch(fullUrl, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) throw new Error(r.statusText);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${name}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast({ kind: "success", title: `Downloaded ${name}.csv` });
    } catch (e) {
      toast({ kind: "error", title: "Download failed", description: (e as Error).message });
    }
  }

  const bearerHint = (
    <div className="rounded-md border border-dashed bg-secondary/30 p-3 text-xs">
      <div className="font-semibold mb-1">Power BI / Tableau / Excel hook-up</div>
      <ol className="list-decimal pl-4 space-y-0.5 text-muted-foreground">
        <li>Use the URL of any feed below.</li>
        <li>Authenticate with bearer token from Settings → My MFA → Token (or login JWT).</li>
        <li>Power BI: <span className="font-mono">Get Data → Web → Advanced → Authorization: Bearer &lt;token&gt;</span></li>
        <li>Tableau: Web Data Connector with bearer token.</li>
      </ol>
    </div>
  );

  const icons: Record<string, React.ReactNode> = {
    findings: <FileSearch className="h-5 w-5" />,
    risk_scores: <Target className="h-5 w-5" />,
    test_runs: <Database className="h-5 w-5" />,
  };

  return (
    <div className="space-y-4">
      <SectionCard
        title="Live BI feeds"
        description="CSV endpoints consumable by Power BI, Tableau, Excel. Re-fetched on each refresh."
      >
        {!manifest ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {manifest.feeds.map((f) => (
              <div key={f.name} className="rounded-lg border bg-card p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-2">
                  {icons[f.name]}
                </div>
                <div className="font-semibold">{f.name.replace(/_/g, " ")}</div>
                <div className="text-[11px] text-muted-foreground font-mono mt-1">{f.url}</div>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => downloadFeed(f.url, f.name)}>
                    <Download className="h-4 w-4" /> Download
                  </Button>
                  <Button
                    size="sm" variant="outline"
                    onClick={() => {
                      const fullUrl = activeProjectId
                        ? `${window.location.origin}${f.url}?project_id=${activeProjectId}`
                        : `${window.location.origin}${f.url}`;
                      navigator.clipboard.writeText(fullUrl);
                      toast({ kind: "success", title: "URL copied" });
                    }}
                  >
                    Copy URL
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
      {bearerHint}
    </div>
  );
}

function SsoTab() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({
    queryKey: ["sso"],
    queryFn: () => api.get<Record<string, unknown>>("/api/settings/sso"),
  });
  const [values, setValues] = useState<Record<string, unknown>>({});
  const config = { ...cfg, ...values };
  const save = useMutation({
    mutationFn: () => api.put("/api/settings/sso", values),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sso"] }),
  });

  if (!cfg) return null;
  const set = (k: string, v: unknown) => setValues({ ...values, [k]: v });

  return (
    <SectionCard
      title="Single sign-on"
      description="OAuth2 auth with Azure AD / Google / Okta / generic OIDC."
      actions={<Button onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save"}
      </Button>}
    >
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2 flex items-center gap-2">
          <input type="checkbox" checked={!!config.enabled}
                 onChange={(e) => set("enabled", e.target.checked)} />
          <Label className="mb-0">Enable SSO</Label>
        </div>
        <div><Label>Provider</Label>
          <Select value={String(config.provider ?? "azure_ad")}
                  onChange={(e) => set("provider", e.target.value)}>
            <option value="azure_ad">Azure AD (Entra ID)</option>
            <option value="google">Google</option>
            <option value="okta">Okta</option>
            <option value="generic_oidc">Generic OIDC</option>
          </Select></div>
        <div><Label>Tenant ID</Label>
          <Input value={String(config.tenant_id ?? "")}
                 onChange={(e) => set("tenant_id", e.target.value)} /></div>
        <div><Label>Client ID</Label>
          <Input value={String(config.client_id ?? "")}
                 onChange={(e) => set("client_id", e.target.value)} /></div>
        <div><Label>Client secret</Label>
          <Input type="password"
                 placeholder={config.client_secret ? "••••••••" : ""}
                 onChange={(e) => set("client_secret", e.target.value)} /></div>
        <div className="col-span-2"><Label>Redirect URI</Label>
          <Input value={String(config.redirect_uri ?? "")}
                 onChange={(e) => set("redirect_uri", e.target.value)}
                 placeholder="https://your.domain/api/auth/sso/callback" /></div>
        <div><Label>Allowed email domains (comma-sep)</Label>
          <Input
            value={(config.allowed_domains as string[] | undefined)?.join(",") ?? ""}
            onChange={(e) => set("allowed_domains", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></div>
        <div><Label>Default role for auto-provisioned users</Label>
          <Select value={String(config.default_role ?? "AUDITOR")}
                  onChange={(e) => set("default_role", e.target.value)}>
            <option value="VIEWER">VIEWER</option>
            <option value="AUDITOR">AUDITOR</option>
            <option value="ADMIN">ADMIN</option>
          </Select></div>
      </div>
    </SectionCard>
  );
}

function EmailTab() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({
    queryKey: ["email"],
    queryFn: () => api.get<Record<string, unknown>>("/api/settings/email"),
  });
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [testTo, setTestTo] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);
  const config = { ...cfg, ...values };
  const save = useMutation({
    mutationFn: () => api.put("/api/settings/email", values),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["email"] }),
  });
  const testSend = useMutation({
    mutationFn: () => api.post("/api/settings/email/test", { to: testTo }),
    onSuccess: () => setTestResult("✅ Sent"),
    onError: (e) => setTestResult("❌ " + (e as Error).message),
  });

  if (!cfg) return null;
  const set = (k: string, v: unknown) => setValues({ ...values, [k]: v });
  const provider = String(config.provider ?? "smtp");

  return (
    <>
      <SectionCard title="Outbound email" actions={
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      }>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 flex items-center gap-2">
            <input type="checkbox" checked={!!config.enabled}
                   onChange={(e) => set("enabled", e.target.checked)} />
            <Label className="mb-0">Enable outbound email</Label>
          </div>
          <div><Label>Provider</Label>
            <Select value={provider} onChange={(e) => set("provider", e.target.value)}>
              <option value="smtp">SMTP (w/ optional XOAUTH2)</option>
              <option value="graph">Microsoft Graph (app-only)</option>
            </Select></div>
          <div><Label>From address</Label>
            <Input value={String(config.from_address ?? "")}
                   onChange={(e) => set("from_address", e.target.value)} /></div>
          <div><Label>From name</Label>
            <Input value={String(config.from_name ?? "")}
                   onChange={(e) => set("from_name", e.target.value)} /></div>

          {provider === "smtp" && (
            <>
              <div><Label>SMTP host</Label>
                <Input value={String(config.smtp_host ?? "")}
                       onChange={(e) => set("smtp_host", e.target.value)} /></div>
              <div><Label>SMTP port</Label>
                <Input type="number" value={Number(config.smtp_port ?? 587)}
                       onChange={(e) => set("smtp_port", Number(e.target.value))} /></div>
              <div><Label>SMTP user</Label>
                <Input value={String(config.smtp_user ?? "")}
                       onChange={(e) => set("smtp_user", e.target.value)} /></div>
              <div><Label>SMTP password</Label>
                <Input type="password" placeholder={config.smtp_password ? "••••••••" : ""}
                       onChange={(e) => set("smtp_password", e.target.value)} /></div>
              <div className="col-span-2 flex items-center gap-2">
                <input type="checkbox" checked={!!config.use_oauth2}
                       onChange={(e) => set("use_oauth2", e.target.checked)} />
                <Label className="mb-0">Use modern-auth (XOAUTH2 client credentials)</Label>
              </div>
            </>
          )}
          {provider === "graph" && (
            <>
              <div><Label>Tenant ID</Label>
                <Input value={String(config.graph_tenant_id ?? "")}
                       onChange={(e) => set("graph_tenant_id", e.target.value)} /></div>
              <div><Label>Client ID</Label>
                <Input value={String(config.graph_client_id ?? "")}
                       onChange={(e) => set("graph_client_id", e.target.value)} /></div>
              <div><Label>Client secret</Label>
                <Input type="password" placeholder="••••••••"
                       onChange={(e) => set("graph_client_secret", e.target.value)} /></div>
              <div><Label>Sender UPN (mailbox)</Label>
                <Input value={String(config.graph_sender_upn ?? "")}
                       onChange={(e) => set("graph_sender_upn", e.target.value)} /></div>
            </>
          )}
        </div>
      </SectionCard>

      <SectionCard title="Send test email" className="mt-4">
        <div className="flex items-end gap-3">
          <div className="flex-1"><Label>To address</Label>
            <Input type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} /></div>
          <Button variant="outline" onClick={() => testSend.mutate()}
                  disabled={!testTo || testSend.isPending}>
            {testSend.isPending ? "Sending…" : "Send test"}
          </Button>
        </div>
        {testResult && <div className="mt-3 text-sm">{testResult}</div>}
      </SectionCard>
    </>
  );
}

function MfaTab() {
  const { user, refresh } = useAuth();
  const qc = useQueryClient();
  const [setup, setSetup] = useState<{ provisioning_uri: string; secret: string } | null>(null);
  const [code, setCode] = useState("");

  const start = useMutation({
    mutationFn: () => api.post<{ provisioning_uri: string; secret: string }>("/api/auth/mfa/setup"),
    onSuccess: (d) => setSetup(d),
  });
  const enable = useMutation({
    mutationFn: () => api.post("/api/auth/mfa/enable", { token: code }),
    onSuccess: () => {
      setSetup(null);
      setCode("");
      refresh();
      qc.invalidateQueries();
    },
  });
  const disable = useMutation({
    mutationFn: () => api.post("/api/auth/mfa/disable", { token: code }),
    onSuccess: () => { setCode(""); refresh(); },
  });

  return (
    <SectionCard title="Two-factor authentication">
      {user?.mfa_enabled ? (
        <>
          <Badge tone="success">Enabled</Badge>
          <div className="mt-4 text-sm">
            MFA is active on your account. To disable, enter a current TOTP code.
          </div>
          <div className="flex items-end gap-3 mt-3">
            <div className="flex-1 max-w-[200px]"><Label>Current TOTP code</Label>
              <Input maxLength={6} value={code} onChange={(e) => setCode(e.target.value)}
                     className="font-mono text-center text-lg tracking-[0.5em]" /></div>
            <Button variant="destructive" onClick={() => disable.mutate()}
                    disabled={code.length !== 6 || disable.isPending}>
              {disable.isPending ? "Disabling…" : "Disable MFA"}
            </Button>
          </div>
        </>
      ) : !setup ? (
        <>
          <Badge tone="muted">Not enabled</Badge>
          <div className="mt-4 text-sm text-muted-foreground">
            Protect your account with a TOTP authenticator app (Google Authenticator, Authy, 1Password, etc.).
          </div>
          <Button onClick={() => start.mutate()} disabled={start.isPending} className="mt-4">
            {start.isPending ? "Setting up…" : "Start MFA setup"}
          </Button>
        </>
      ) : (
        <>
          <div className="text-sm">
            Scan this URI with your authenticator app, then enter the 6-digit code.
          </div>
          <div className="mt-3 rounded-md bg-secondary p-3 font-mono text-xs break-all">
            {setup.provisioning_uri}
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            Or enter secret manually: <code className="bg-secondary px-1 rounded">{setup.secret}</code>
          </div>
          <div className="flex items-end gap-3 mt-4">
            <div className="flex-1 max-w-[200px]"><Label>Code from app</Label>
              <Input maxLength={6} value={code} onChange={(e) => setCode(e.target.value)}
                     className="font-mono text-center text-lg tracking-[0.5em]" /></div>
            <Button onClick={() => enable.mutate()} disabled={code.length !== 6 || enable.isPending}>
              {enable.isPending ? "Verifying…" : "Enable"}
            </Button>
          </div>
        </>
      )}
    </SectionCard>
  );
}

function RetentionTab() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({
    queryKey: ["retention"],
    queryFn: () => api.get<Record<string, unknown>>("/api/settings/retention"),
  });
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [scan, setScan] = useState<unknown | null>(null);
  const [confirm, setConfirm] = useState(false);
  const config = { ...cfg, ...values };
  const save = useMutation({
    mutationFn: () => api.put("/api/settings/retention", values),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["retention"] }),
  });
  const scanNow = useMutation({
    mutationFn: () => api.post<unknown>("/api/settings/retention/scan"),
    onSuccess: (d) => setScan(d),
  });
  const purge = useMutation({
    mutationFn: () => api.post<unknown>("/api/settings/retention/purge"),
    onSuccess: (d) => setScan(d),
  });
  if (!cfg) return null;
  const set = (k: string, v: unknown) => setValues({ ...values, [k]: v });

  return (
    <>
      <SectionCard title="Retention policy"
        actions={<Button onClick={() => save.mutate()} disabled={save.isPending}>Save</Button>}>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 flex items-center gap-2">
            <input type="checkbox" checked={!!config.enabled}
                   onChange={(e) => set("enabled", e.target.checked)} />
            <Label className="mb-0">Enable retention purge</Label>
          </div>
          <div><Label>Default retention (days)</Label>
            <Input type="number" value={Number(config.default_days ?? 2555)}
                   onChange={(e) => set("default_days", Number(e.target.value))} /></div>
          <div className="col-span-2 flex items-center gap-2">
            <input type="checkbox" checked={!!config.preserve_findings_referenced}
                   onChange={(e) => set("preserve_findings_referenced", e.target.checked)} />
            <Label className="mb-0">Preserve datasets referenced by open findings</Label>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Scan + purge" className="mt-4">
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => scanNow.mutate()}>Scan (dry-run)</Button>
          <label className="flex items-center gap-2 ml-auto text-sm text-muted-foreground">
            <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            I understand this irreversibly deletes stale data
          </label>
          <Button variant="destructive" disabled={!confirm || purge.isPending}
                  onClick={() => purge.mutate()}>Purge now</Button>
        </div>
        {scan != null && (
          <pre className="mt-4 bg-secondary rounded-md p-3 text-xs overflow-auto max-h-[320px]">
            {JSON.stringify(scan, null, 2)}
          </pre>
        )}
      </SectionCard>
    </>
  );
}

function SiemTab() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({
    queryKey: ["siem"],
    queryFn: () => api.get<Record<string, unknown>>("/api/settings/siem"),
  });
  const [values, setValues] = useState<Record<string, unknown>>({});
  const config = { ...cfg, ...values };
  const save = useMutation({
    mutationFn: () => api.put("/api/settings/siem", values),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["siem"] }),
  });
  if (!cfg) return null;
  const set = (k: string, v: unknown) => setValues({ ...values, [k]: v });

  return (
    <SectionCard
      title="SIEM / syslog webhook"
      description="Fire-and-forget HTTP POST of every audit_log entry to your collector (Splunk HEC, Sentinel, Chronicle)."
      actions={<Button onClick={() => save.mutate()}>Save</Button>}
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <input type="checkbox" checked={!!config.enabled}
                 onChange={(e) => set("enabled", e.target.checked)} />
          <Label className="mb-0">Enable outbound SIEM feed</Label>
        </div>
        <div><Label>Collector URL</Label>
          <Input value={String(config.url ?? "")}
                 onChange={(e) => set("url", e.target.value)}
                 placeholder="https://collector.example.com/audit-sink" /></div>
        <div><Label>Authorization header</Label>
          <Input type="password"
                 placeholder={config.auth_header === "***REDACTED***" ? "••••••• (set)" : ""}
                 onChange={(e) => set("auth_header", e.target.value)} /></div>
      </div>
    </SectionCard>
  );
}
