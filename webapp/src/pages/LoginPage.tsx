import { AlertCircle, Shield } from "lucide-react";
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

export function LoginPage() {
  const { user, login, verifyMfa } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [challenge, setChallenge] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(username, password);
      if (res.mfaRequired) setChallenge(res.challenge!);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function onMfa(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await verifyMfa(challenge!, mfaCode);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full grid lg:grid-cols-2 bg-background">
      {/* Brand side */}
      <div className="hidden lg:flex flex-col justify-between bg-gradient-to-br from-primary via-primary to-[#0f4a5a] text-white p-12">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-md bg-accent/20 flex items-center justify-center">
            <Shield className="h-5 w-5 text-accent" />
          </div>
          <div>
            <div className="font-semibold">TechSource Audit</div>
            <div className="text-xs text-white/60 uppercase tracking-wider">Group intelligence</div>
          </div>
        </div>

        <div className="max-w-md">
          <h1 className="text-3xl font-semibold leading-tight">
            Group-wide internal audit intelligence.
          </h1>
          <p className="mt-3 text-white/80 leading-relaxed">
            148 named tests across 11 subledger domains, tamper-evident audit log,
            ensemble risk scoring, continuous monitoring — all in one platform.
          </p>
          <div className="grid grid-cols-3 gap-6 mt-10">
            <div>
              <div className="text-3xl font-semibold tracking-tight">148</div>
              <div className="text-xs text-white/60 uppercase tracking-wider mt-1">Named tests</div>
            </div>
            <div>
              <div className="text-3xl font-semibold tracking-tight">36</div>
              <div className="text-xs text-white/60 uppercase tracking-wider mt-1">Detectors</div>
            </div>
            <div>
              <div className="text-3xl font-semibold tracking-tight">10</div>
              <div className="text-xs text-white/60 uppercase tracking-wider mt-1">Domain packs</div>
            </div>
          </div>
        </div>

        <div className="text-xs text-white/50">
          Audit integrity is hash-chained. Every action is logged and verifiable.
        </div>
      </div>

      {/* Form side */}
      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex lg:hidden items-center gap-2.5">
            <Shield className="h-6 w-6 text-accent" />
            <span className="text-lg font-semibold">TechSource Audit</span>
          </div>
          <h2 className="text-2xl font-semibold">{challenge ? "Two-factor" : "Sign in"}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {challenge
              ? "Enter the 6-digit code from your authenticator app."
              : "Use your corporate credentials."}
          </p>

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}

          {!challenge ? (
            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              <div>
                <Label htmlFor="u">Username</Label>
                <Input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
              </div>
              <div>
                <Label htmlFor="p">Password</Label>
                <Input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Signing in…" : "Sign in"}
              </Button>
              <div className="text-xs text-center text-muted-foreground">
                Single sign-on and passkey support are configurable by your admin.
              </div>
            </form>
          ) : (
            <form onSubmit={onMfa} className="mt-6 space-y-4">
              <div>
                <Label htmlFor="mfa">Authenticator code</Label>
                <Input
                  id="mfa"
                  maxLength={6}
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  className="font-mono text-center text-lg tracking-[0.5em]"
                  autoFocus
                />
              </div>
              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Verifying…" : "Verify"}
              </Button>
              <button
                type="button"
                onClick={() => setChallenge(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Back to sign-in
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
