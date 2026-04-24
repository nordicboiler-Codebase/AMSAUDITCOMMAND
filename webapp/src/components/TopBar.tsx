import { useQuery } from "@tanstack/react-query";
import { ChevronDown, FolderKanban, LogOut, Settings as SettingsIcon, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface Props {
  activeProjectId: string | null;
  onActiveProjectChange: (id: string | null) => void;
}

export function TopBar({ activeProjectId, onActiveProjectChange }: Props) {
  const { user, logout } = useAuth();
  const [projectOpen, setProjectOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const projectRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/api/projects"),
  });

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (projectRef.current && !projectRef.current.contains(e.target as Node)) {
        setProjectOpen(false);
      }
      if (userRef.current && !userRef.current.contains(e.target as Node)) {
        setUserOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const initials = (user?.username || "?")
    .split(/[\s._-]+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="h-14 border-b bg-card/70 backdrop-blur-sm sticky top-0 z-30 flex items-center justify-between px-6 gap-4">
      {/* Active project picker */}
      <div ref={projectRef} className="relative">
        <button
          onClick={() => setProjectOpen((v) => !v)}
          className={cn(
            "flex items-center gap-2.5 h-9 px-3 rounded-lg border border-border bg-card",
            "text-sm hover:bg-secondary transition-colors",
          )}
        >
          <FolderKanban className="h-4 w-4 text-muted-foreground" />
          <div className="text-left min-w-0">
            <div className="text-[10px] uppercase tracking-[0.1em] text-muted-foreground font-semibold leading-none">
              Active project
            </div>
            <div className="text-[13px] font-medium leading-tight truncate max-w-[200px]">
              {activeProject?.name ?? "None selected"}
            </div>
          </div>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>

        {projectOpen && (
          <div className="absolute left-0 top-full mt-2 w-[340px] rounded-lg border bg-card shadow-lg overflow-hidden animate-slide-in">
            <div className="px-3 py-2 border-b text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
              Switch project
            </div>
            <div className="max-h-[360px] overflow-auto py-1">
              <button
                onClick={() => {
                  onActiveProjectChange(null);
                  setProjectOpen(false);
                }}
                className={cn(
                  "w-full text-left px-3 py-2 text-sm hover:bg-secondary",
                  !activeProjectId && "bg-accent/10 text-accent font-medium",
                )}
              >
                <div className="text-xs text-muted-foreground">None</div>
                <div className="text-sm">Don't scope to a project</div>
              </button>
              {projects.length === 0 ? (
                <div className="px-3 py-4 text-sm text-muted-foreground text-center">
                  No projects yet.{" "}
                  <Link to="/projects" className="text-accent hover:underline"
                        onClick={() => setProjectOpen(false)}>
                    Create one →
                  </Link>
                </div>
              ) : (
                projects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      onActiveProjectChange(p.id);
                      setProjectOpen(false);
                    }}
                    className={cn(
                      "w-full text-left px-3 py-2 text-sm hover:bg-secondary",
                      activeProjectId === p.id && "bg-accent/10 text-accent font-medium",
                    )}
                  >
                    <div className="text-xs text-muted-foreground">
                      {p.subsidiary_code || "—"}
                    </div>
                    <div className="text-sm truncate">{p.name}</div>
                  </button>
                ))
              )}
            </div>
            <Link
              to="/projects"
              onClick={() => setProjectOpen(false)}
              className="block px-3 py-2 text-sm border-t bg-secondary/40 hover:bg-secondary text-center text-accent font-medium"
            >
              Manage projects →
            </Link>
          </div>
        )}
      </div>

      {/* User menu */}
      <div ref={userRef} className="relative">
        <button
          onClick={() => setUserOpen((v) => !v)}
          className="flex items-center gap-2 h-9 pl-2 pr-3 rounded-lg hover:bg-secondary transition-colors"
        >
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-primary to-accent text-white font-semibold flex items-center justify-center text-xs">
            {initials}
          </div>
          <div className="text-left">
            <div className="text-[13px] font-medium leading-tight">{user?.username}</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground leading-none mt-0.5">
              {user?.role}
            </div>
          </div>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>

        {userOpen && (
          <div className="absolute right-0 top-full mt-2 w-64 rounded-lg border bg-card shadow-lg overflow-hidden animate-slide-in">
            <div className="p-4 border-b">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-primary to-accent text-white font-semibold flex items-center justify-center text-sm">
                  {initials}
                </div>
                <div className="min-w-0">
                  <div className="font-medium text-sm truncate">{user?.username}</div>
                  <div className="text-xs text-muted-foreground truncate">{user?.email}</div>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <span className="inline-flex items-center rounded-full bg-accent/15 text-accent px-2 py-0.5 text-[11px] font-semibold">
                  {user?.role}
                </span>
                {user?.mfa_enabled && (
                  <span className="inline-flex items-center rounded-full bg-success/15 text-success px-2 py-0.5 text-[11px] font-semibold">
                    MFA
                  </span>
                )}
              </div>
            </div>
            <div className="py-1">
              <Link
                to="/settings"
                onClick={() => setUserOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-secondary"
              >
                <SettingsIcon className="h-4 w-4 text-muted-foreground" />
                Settings
              </Link>
              <Link
                to="/admin"
                onClick={() => setUserOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-secondary"
              >
                <User className="h-4 w-4 text-muted-foreground" />
                Users
              </Link>
              <button
                onClick={() => { setUserOpen(false); logout(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-destructive/10 text-destructive border-t mt-1"
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
