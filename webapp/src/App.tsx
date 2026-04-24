import { Loader2 } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useAuth } from "./lib/auth";
import { AuditLogPage } from "./pages/AuditLogPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FindingsPage } from "./pages/FindingsPage";
import { LoginPage } from "./pages/LoginPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RiskExplorerPage } from "./pages/RiskExplorerPage";
import { SubsidiariesPage } from "./pages/SubsidiariesPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="findings" element={<FindingsPage />} />
        <Route path="risk" element={<RiskExplorerPage />} />
        <Route path="subsidiaries" element={<SubsidiariesPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="audit-log" element={<AuditLogPage />} />
        <Route path="engagements" element={<PlaceholderPage title="Engagements" description="Workpaper bundles + maker-checker finalise." />} />
        <Route path="schedules" element={<PlaceholderPage title="Schedules" description="Cron-driven pack runs + alerts." />} />
        <Route path="datasets" element={<PlaceholderPage title="Datasets" description="Encrypted uploads, hashed, classifiable." />} />
        <Route path="run" element={<PlaceholderPage title="Run tests" description="Execute templates, packs, or custom detectors." />} />
        <Route path="runs" element={<PlaceholderPage title="Test runs" description="Every run logged with input/output hashes." />} />
        <Route path="templates" element={<PlaceholderPage title="Templates" description="148 named audit tests across 11 subledger domains." />} />
        <Route path="packs" element={<PlaceholderPage title="Packs" description="10 domain packs covering AP, AR, GL, Payroll, etc." />} />
        <Route path="ml-feedback" element={<PlaceholderPage title="ML Feedback" description="Precision per detector from labelled findings." />} />
        <Route path="admin" element={<PlaceholderPage title="Users" description="Directory of platform users + SCIM provisioning." />} />
        <Route path="settings" element={<PlaceholderPage title="Settings" description="SSO, MFA, Email, Retention, SIEM, Branding." />} />
      </Route>
    </Routes>
  );
}
