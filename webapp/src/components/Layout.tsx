import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function Layout() {
  const [activeProjectId, setActiveProjectId] = useState<string | null>(
    () => localStorage.getItem("ts_active_project") || null,
  );
  const setProject = (id: string | null) => {
    setActiveProjectId(id);
    if (id) localStorage.setItem("ts_active_project", id);
    else localStorage.removeItem("ts_active_project");
  };
  return (
    <div className="h-full flex bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopBar
          activeProjectId={activeProjectId}
          onActiveProjectChange={setProject}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-[1440px] mx-auto px-8 py-6">
            <Outlet context={{ activeProjectId }} />
          </div>
        </main>
      </div>
    </div>
  );
}
