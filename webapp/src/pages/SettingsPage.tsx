import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, Download, FileSearch, Sparkles, Target, XCircle } from "lucide-react";
import { useOutletContext } from "react-router-dom";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api, getToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";

type Tab = "sso" | "email" | "mfa" | "retention" | "siem" | "bi" | "ai";

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("ai");
  return (
    <>
      <PageHeader title="Settings" description="Platform configuration — AI providers, SSO, email, MFA, retention, SIEM, BI feeds." />
      <div className="flex gap-1 border-b mb-5 flex-wrap">
        {([
          ["ai", "AI Providers"],
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
            {k === "ai" && <Sparkles className="h-3.5 w-3.5 inline -translate-y-px mr-1 text-accent" />}
            {label}
          </button>
        ))}
      </div>
      {tab === "ai" && <AiProvidersTab />}
      {tab === "sso" && <SsoTab />}
      {tab === "email" && <EmailTab />}
      {tab === "mfa" && <MfaTab />}
      {tab === "retention" && <RetentionTab />}
      {tab === "siem" && <SiemTab />}
      {tab === "bi" && <BiTab />}
    </>
  );
}

interface AiProvider {
  provider: "anthropic" | "openai" | "gemini";
  label: string;
  key_hint: string;
  enabled: boolean;
  configured: boolean;
  sdk_installed: boolean;
  model: string;
  model_choices: string[];
  default_model: string;
  api_key: string;
}

interface AiSettingsResponse {
  active: string | null;
  enabled: boolean;
  reason: string;
  model: string | null;
  legacy_env_active: boolean;
  providers: AiProvider[];
}

const PROVIDER_DOC_URL: Record<string, string> = {
  anthropic: "https://console.anthropic.com/settings/keys",
  openai: "https://platform.openai.com/api-keys",
  gemini: "https://aistudio.google.com/apikey",
};

function AiProvidersTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: settings } = useQuery({
    queryKey: ["ai-settings"],
    queryFn: () => api.get<AiSettingsResponse>("/api/settings/ai"),
  });

  // Working copy — gets seeded from server data, edited locally, saved on demand.
  const [draft, setDraft] = useState<Record<string, AiProvider>>({});
  const [active, setActive] = useState<string>("");
  const [editingKeys, setEditingKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (settings) {
      const map: Record<string, AiProvider> = {};
      for (const p of settings.providers) map[p.provider] = p;
      setDraft(map);
      setActive(settings.active || "");
    }
  }, [settings]);

  const save = useMutation({
    mutationFn: () => {
      const providersBody: Record<string, unknown> = {};
      for (const p of Object.values(draft)) {
        providersBody[p.provider] = {
          enabled: p.enabled,
          model: p.model,
          // Only send api_key if user actually edited it; otherwise null = leave unchanged
          api_key: editingKeys[p.provider] ? p.api_key || "" : null,
        };
      }
      return api.put<AiSettingsResponse>("/api/settings/ai", {
        active: active || "",
        providers: providersBody,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-settings"] });
      qc.invalidateQueries({ queryKey: ["ai-status"] });
      setEditingKeys({});
      toast({ kind: "success", title: "AI settings saved" });
    },
    onError: (e) => toast({
      kind: "error", title: "Save failed",
      description: (e as Error).message,
    }),
  });

  const test = useMutation({
    mutationFn: (provider: string) =>
      api.post<{ ok: boolean; model?: string; sample?: string; error?: string }>(
        `/api/settings/ai/${provider}/test`,
      ),
    onSuccess: (r) => {
      if (r.ok) {
        toast({
          kind: "success", title: "Provider OK",
          description: `${r.model} replied: ${r.sample}`,
        });
      } else {
        toast({ kind: "error", title: "Provider test failed", description: r.error });
      }
    },
    onError: (e) => toast({
      kind: "error", title: "Test failed", description: (e as Error).message,
    }),
  });

  if (!settings) return <div className="text-sm text-muted-foreground">Loading…</div>;

  const update = (provider: string, patch: Partial<AiProvider>) => {
    setDraft((d) => ({ ...d, [provider]: { ...d[provider], ...patch } }));
  };

  return (
    <div className="space-y-4">
      <div className={`rounded-md border p-3 flex items-center gap-3 ${
        settings.enabled
          ? "border-success/30 bg-success/5"
          : "border-warning/30 bg-warning/5"
      }`}>
        {settings.enabled
          ? <CheckCircle2 className="h-5 w-5 text-success" />
          : <XCircle className="h-5 w-5 text-warning" />}
        <div className="text-sm">
          <div className="font-semibold">
            {settings.enabled
              ? `AI on — ${settings.providers.find(p => p.provider === settings.active)?.label} · ${settings.model}`
              : "AI off"}
          </div>
          <div className="text-xs text-muted-foreground">{settings.reason}</div>
          {settings.legacy_env_active && (
            <div className="text-[11px] text-muted-foreground mt-0.5">
              Currently using ANTHROPIC_API_KEY from .env (legacy). Configuring a
              provider here will take precedence.
            </div>
          )}
        </div>
      </div>

      <SectionCard title="Active provider" description="Which provider Claude features in this app should call.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {settings.providers.map((p) => {
            const can = (draft[p.provider]?.configured || editingKeys[p.provider]) && draft[p.provider]?.sdk_installed && draft[p.provider]?.enabled;
            return (
              <label
                key={p.provider}
                className={`rounded-md border p-3 cursor-pointer transition-all ${
                  active === p.provider
                    ? "ring-2 ring-accent border-accent bg-accent/5"
                    : "hover:bg-secondary/30"
                } ${!can ? "opacity-60" : ""}`}
              >
                <div className="flex items-start gap-2">
                  <input
                    type="radio" name="active-provider"
                    checked={active === p.provider}
                    onChange={() => setActive(p.provider)}
                    disabled={!can}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold">{p.label}</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      {can
                        ? `Ready · ${draft[p.provider]?.model}`
                        : !p.sdk_installed
                          ? "SDK not installed"
                          : !p.configured && !editingKeys[p.provider]
                            ? "Not configured"
                            : !p.enabled
                              ? "Disabled below"
                              : "Configure below"}
                    </div>
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </SectionCard>

      {settings.providers.map((p) => (
        <SectionCard
          key={p.provider}
          title={p.label}
          description={p.key_hint}
          actions={
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border ${
                  p.sdk_installed
                    ? "border-success/30 bg-success/10 text-success"
                    : "border-destructive/30 bg-destructive/10 text-destructive"
                }`}
              >
                SDK {p.sdk_installed ? "OK" : "missing"}
              </span>
              {p.configured && (
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border border-success/30 bg-success/10 text-success">
                  key set
                </span>
              )}
              <Button
                variant="outline" size="sm"
                onClick={() => test.mutate(p.provider)}
                disabled={!p.configured || !p.sdk_installed || test.isPending}
                title="Run a tiny ping call to verify the key works"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {test.isPending && test.variables === p.provider ? "Testing…" : "Test"}
              </Button>
            </div>
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label>API key</Label>
              <div className="flex gap-2">
                <Input
                  type={editingKeys[p.provider] ? "text" : "password"}
                  value={
                    editingKeys[p.provider]
                      ? (draft[p.provider]?.api_key || "")
                      : (p.configured ? "••••••••••••••••" : "")
                  }
                  onChange={(e) => update(p.provider, { api_key: e.target.value })}
                  disabled={!editingKeys[p.provider]}
                  placeholder={`Paste your ${p.label} key…`}
                  className="font-mono text-xs"
                />
                {editingKeys[p.provider] ? (
                  <Button
                    variant="outline" size="sm"
                    onClick={() => {
                      setEditingKeys((e) => ({ ...e, [p.provider]: false }));
                      update(p.provider, { api_key: "" });
                    }}
                  >
                    Cancel
                  </Button>
                ) : (
                  <Button
                    variant="outline" size="sm"
                    onClick={() => setEditingKeys((e) => ({ ...e, [p.provider]: true }))}
                  >
                    {p.configured ? "Replace" : "Set key"}
                  </Button>
                )}
              </div>
              <a
                href={PROVIDER_DOC_URL[p.provider]} target="_blank" rel="noreferrer"
                className="text-[11px] text-accent hover:underline mt-1 inline-block"
              >
                Get a key →
              </a>
            </div>

            <div>
              <Label>Model</Label>
              <Select
                value={draft[p.provider]?.model ?? p.model}
                onChange={(e) => update(p.provider, { model: e.target.value })}
              >
                {p.model_choices.map((m) => (
                  <option key={m} value={m}>{m}{m === p.default_model ? " (default)" : ""}</option>
                ))}
              </Select>
            </div>

            <div className="md:col-span-2 flex items-center gap-2">
              <input
                type="checkbox" id={`enabled-${p.provider}`}
                checked={draft[p.provider]?.enabled ?? p.enabled}
                onChange={(e) => update(p.provider, { enabled: e.target.checked })}
              />
              <Label htmlFor={`enabled-${p.provider}`} className="mb-0">
                Enable this provider (must also be selected as active above to be used)
              </Label>
            </div>
          </div>
        </SectionCard>
      ))}

      <div className="flex justify-end gap-2">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save AI settings"}
        </Button>
      </div>

      <div className="text-[11px] text-muted-foreground">
        Keys are encrypted with the platform Fernet keychain at rest. Every Claude call
        is logged to the tamper-evident audit chain (provider, model, prompt outcome,
        chosen template). Rate limited to 30 requests/minute/IP.
      </div>
    </div>
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
