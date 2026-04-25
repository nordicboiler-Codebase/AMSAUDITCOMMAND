import { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastKind = "success" | "error" | "info";
interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
}

interface ToastContextValue {
  toast: (t: Omit<Toast, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 4500);
  }, []);
  const dismiss = (id: string) =>
    setToasts((prev) => prev.filter((x) => x.id !== id));
  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto animate-slide-in flex items-start gap-3",
              "min-w-[320px] max-w-[420px] rounded-lg border bg-card shadow-lg p-3.5",
              t.kind === "success" && "border-success/30",
              t.kind === "error" && "border-destructive/30",
              t.kind === "info" && "border-border",
            )}
          >
            {t.kind === "success" && (
              <CheckCircle2 className="h-5 w-5 text-success shrink-0 mt-0.5" />
            )}
            {t.kind === "error" && (
              <XCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
            )}
            {t.kind === "info" && (
              <Info className="h-5 w-5 text-accent shrink-0 mt-0.5" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">{t.title}</div>
              {t.description && (
                <div className="text-xs text-muted-foreground mt-1">{t.description}</div>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be inside ToastProvider");
  return ctx;
}
