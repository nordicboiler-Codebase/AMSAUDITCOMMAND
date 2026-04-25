import {
  Activity, Building2, Cable, Clock, Database, FileSearch, FolderKanban,
  History, LayoutDashboard, Package, Play, Settings, Shield, ShieldCheck,
  Sparkles, Target, Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";
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
      { to: "/connectors", label: "Connectors", icon: Cable },
      { to: "/run", label: "Run tests", icon: Play },
      { to: "/risk", label: "Risk Explorer", icon: Target },
      { to: "/runs", label: "Test runs", icon: History },
      { to: "/monitors", label: "Monitors", icon: Activity },
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

export function Sidebar() {
  return (
    <aside className="w-[228px] shrink-0 bg-sidebar text-sidebar-foreground border-r border-sidebar-border flex flex-col">
      {/* Brand */}
      <div className="p-4 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-lg bg-accent/20 flex items-center justify-center shrink-0">
            <Shield className="h-4.5 w-4.5 text-accent" />
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-white leading-tight">
              TechSource Audit
            </div>
            <div className="text-[9.5px] uppercase tracking-[0.12em] text-sidebar-muted leading-tight mt-0.5">
              Group intelligence
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {NAV.map((group, i) => (
          <div key={group.label} className={cn("pb-1", i > 0 && "pt-2")}>
            <div className="text-[9.5px] uppercase tracking-[0.14em] font-semibold text-sidebar-muted/70 px-2.5 pb-1.5">
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
                    "transition-colors border-l-[3px] -ml-px",
                    isActive
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-transparent text-sidebar-foreground/75 hover:bg-white/[0.06] hover:text-white",
                  )
                }
              >
                <Icon className="h-[15px] w-[15px] shrink-0" />
                <span className="truncate">{label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="p-3 border-t border-sidebar-border text-[10px] text-sidebar-muted/60 leading-relaxed">
        <div className="flex items-center gap-1.5">
          <div className="h-1.5 w-1.5 rounded-full bg-success" />
          <span>All systems operational</span>
        </div>
      </div>
    </aside>
  );
}
