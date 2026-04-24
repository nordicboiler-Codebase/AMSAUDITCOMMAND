import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, type User } from "./api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<{ mfaRequired?: boolean; challenge?: string }>;
  verifyMfa: (challenge: string, code: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<User>("/api/auth/me");
      setUser(me);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      const body = new URLSearchParams({ username, password });
      const res: { access_token?: string; mfa_required?: boolean; challenge_token?: string } =
        await api.postForm("/api/auth/token", body);
      if (res.mfa_required) {
        return { mfaRequired: true, challenge: res.challenge_token };
      }
      setToken(res.access_token!);
      const me = await api.get<User>("/api/auth/me");
      setUser(me);
      return {};
    },
    [],
  );

  const verifyMfa = useCallback(async (challenge: string, code: string) => {
    const res = await api.post<{ access_token: string }>("/api/auth/mfa/verify", {
      challenge_token: challenge,
      token: code,
    });
    setToken(res.access_token);
    const me = await api.get<User>("/api/auth/me");
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, verifyMfa, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
