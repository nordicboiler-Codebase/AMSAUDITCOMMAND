import { Loader2 } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useAuth } from "./lib/auth";
import { AdminPage } from "./pages/AdminPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { EngagementsPage } from "./pages/EngagementsPage";
import { FindingDetailPage } from "./pages/FindingDetailPage";
import { FindingsPage } from "./pages/FindingsPage";
import { LoginPage } from "./pages/LoginPage";
import { MLFeedbackPage } from "./pages/MLFeedbackPage";
import { PacksPage } from "./pages/PacksPage";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { MonitorsPage } from "./pages/MonitorsPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RiskExplorerPage } from "./pages/RiskExplorerPage";
import { RunPage } from "./pages/RunPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SubsidiariesPage } from "./pages/SubsidiariesPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { TestRunsPage } from "./pages/TestRunsPage";

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
      <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<DashboardPage />} />
        <Route path="engagements" element={<EngagementsPage />} />
        <Route path="findings" element={<FindingsPage />} />
        <Route path="findings/:id" element={<FindingDetailPage />} />
        <Route path="schedules" element={<SchedulesPage />} />
        <Route path="datasets" element={<DatasetsPage />} />
        <Route path="connectors" element={<ConnectorsPage />} />
        <Route path="monitors" element={<MonitorsPage />} />
        <Route path="run" element={<RunPage />} />
        <Route path="risk" element={<RiskExplorerPage />} />
        <Route path="runs" element={<TestRunsPage />} />
        <Route path="templates" element={<TemplatesPage />} />
        <Route path="packs" element={<PacksPage />} />
        <Route path="subsidiaries" element={<SubsidiariesPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="audit-log" element={<AuditLogPage />} />
        <Route path="ml-feedback" element={<MLFeedbackPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
