import { useQuery } from "@tanstack/react-query";
import {
  BarChart3, Building2, Clock, Database, FileSearch, FolderKanban, Gauge,
  History, LayoutDashboard, LogOut, Package, Play, Settings, Shield,
  ShieldCheck, SlidersHorizontal, Sparkles, Target, Users, Wrench,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { api, type Project } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: React.ElementType;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    label: "Overview",
    items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Audit workflow",
    items: [
      { to: "/engagements", label: "Engagements", icon: FolderKanban },
      { to: "/findings", label: "Findings", icon: FileSearch },
      { to: "/schedules", label: "Schedules", icon: Clock },
    ],
  },
  {
    label: "Data & analysis",
    items: [
      { to: "/datasets", label: "Datasets", icon: Database },
      { to: "/run", label: "Run tests", icon: Play },
      { to: "/risk", label: "Risk Explorer", icon: Target },
      { to: "/runs", label: "Test runs", icon: History },
    ],
  },
  {
    label: "Library",
    items: [
      { to: "/templates", label: "Templates", icon: Package },
      { to: "/packs", label: "Packs", icon: Package },
    ],
  },
  {
    label: "Governance",
    items: [
      { to: "/subsidiaries", label: "Subsidiaries", icon: Building2 },
      { to: "/projects", label: "Projects", icon: FolderKanban },
      { to: "/audit-log", label: "Audit log", icon: ShieldCheck },
    ],
  },
  {
    label: "Insights",
    items: [{ to: "/ml-feedback", label: "ML Feedback", icon: Sparkles }],
  },
  {
    label: "Admin",
    items: [
      { to: "/admin", label: "Users", icon: Users },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function Sidebar({
  activeProjectId,
  onActiveProjectChange,
}: {
  activeProjectId: string | null;
  onActiveProjectChange: (id: string | null) => void;
}) {
  const { user, logout } = useAuth();
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/api/projects"),
  });
  const projects = projectsQuery.data ?? [];

  return (
    <aside className="w-[248px] shrink-0 bg-sidebar text-sidebar-foreground border-r border-sidebar-border flex flex-col">
      {/* Brand */}
      <div className="p-4 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-md bg-accent/20 flex items-center justify-center">
            <Shield className="h-4 w-4 text-accent" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-white leading-tight">TechSource Audit</div>
            <div className="text-[10px] uppercase tracking-wider text-sidebar-muted">
              Group intelligence
            </div>
          </div>
        </div>
      </div>

      {/* User + active project */}
      <div className="p-3 space-y-3 border-b border-sidebar-border">
        <div className="rounded-md bg-white/[0.04] border border-white/[0.06] p-2.5">
          <div className="text-sm font-medium text-white leading-tight truncate">
            {user?.username}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-sidebar-muted mt-0.5">
            {user?.role}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-sidebar-muted mb-1.5 px-1">
            Active project
          </div>
          <select
            value={activeProjectId ?? ""}
            onChange={(e) => onActiveProjectChange(e.target.value || null)}
            className={cn(
              "w-full h-8 px-2 rounded-md bg-white/[0.04] border border-white/[0.08]",
              "text-sm text-white focus:outline-none focus:border-accent/60",
            )}
          >
            <option value="" className="text-foreground">(none)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id} className="text-foreground">
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        {NAV.map((group) => (
          <div key={group.label} className="pb-2">
            <div className="text-[10px] uppercase tracking-[0.12em] font-semibold text-sidebar-muted/70 px-2 pt-2 pb-1">
              {group.label}
            </div>
            {group.items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] font-medium",
                    "transition-colors border-l-[3px]",
                    isActive
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-transparent text-sidebar-foreground/70 hover:bg-white/[0.06] hover:text-white",
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* Sign out */}
      <div className="p-3 border-t border-sidebar-border">
        <button
          onClick={logout}
          className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium text-destructive-foreground bg-destructive/20 hover:bg-destructive/30 border border-destructive/30 transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
