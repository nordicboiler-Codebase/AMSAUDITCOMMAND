const STORAGE_KEY = "ts_audit_token";

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(STORAGE_KEY, token);
  else localStorage.removeItem(STORAGE_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let finalBody: BodyInit | undefined;
  if (body instanceof FormData) {
    finalBody = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    finalBody = JSON.stringify(body);
  }

  const res = await fetch(path, { method, headers, body: finalBody });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return null as T;
  const text = await res.text();
  if (!text) return null as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return JSON.parse(text) as T;
  return text as unknown as T;
}

export const api = {
  get: <T = unknown>(path: string) => request<T>("GET", path),
  post: <T = unknown>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T = unknown>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T = unknown>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T = unknown>(path: string) => request<T>("DELETE", path),
  postForm: async (path: string, formData: URLSearchParams) => {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/x-www-form-urlencoded",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(path, { method: "POST", headers, body: formData });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail || JSON.stringify(data);
      } catch {}
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },
};

// Domain types
export interface User {
  id: string;
  username: string;
  email: string;
  role: "ADMIN" | "AUDITOR" | "VIEWER";
  mfa_enabled: boolean;
  session_expires_at?: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  subsidiary_code?: string;
  status: string;
  owner_id?: string;
  brand_primary?: string;
}

export interface Subsidiary {
  id: string;
  code: string;
  name: string;
  country?: string;
  industry?: string;
  risk_rating?: string;
  segment?: string;
  is_active: boolean;
}

export interface SubsidiaryRollup {
  code: string;
  name: string;
  country?: string;
  segment?: string;
  risk_rating?: string;
  projects: number;
  datasets: number;
  findings_open: number;
  findings_high_critical: number;
  max_risk_score: number;
  test_runs: number;
}

export interface DashboardMetrics {
  projects: number;
  datasets: number;
  engagements_in_progress: number;
  findings_open: number;
  findings_high_or_critical: number;
  findings_this_month: number;
  runs_this_week: number;
  schedules_active: number;
  findings_by_severity: Record<string, number>;
  findings_by_status: Record<string, number>;
  top_risk_records: Array<{
    record_key: string;
    score: number;
    detectors: string[];
  }>;
  finding_trend_last_84d: Array<{ week: string; count: number }>;
}

export interface Finding {
  id: string;
  code: string;
  title: string;
  description?: string;
  project_id: string;
  dataset_id?: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: string;
  risk_score?: number;
  owner_id?: string;
  reviewer_id?: string;
  due_date?: string;
  tags: string[];
  record_keys: string[];
  linked_template_codes: string[];
  created_at?: string;
  reviewed_at?: string;
  closed_at?: string;
}

export interface RiskScore {
  record_key: string;
  score: number;
  contributing_detectors: Array<{
    detector_name: string;
    template_code?: string;
    reason?: string;
    weight?: number;
  }>;
}

export interface Dataset {
  id: string;
  name: string;
  source_filename: string;
  source_hash: string;
  subledger_type: string;
  record_count: number;
  parquet_available?: boolean;
}

export interface TestRun {
  id: string;
  template_code?: string;
  detector_name: string;
  status: string;
  findings_count: number;
  started_at?: string;
  finished_at?: string;
  params?: Record<string, unknown>;
  input_hash?: string;
  output_hash?: string;
  summary?: Record<string, unknown>;
  error_message?: string | null;
}
