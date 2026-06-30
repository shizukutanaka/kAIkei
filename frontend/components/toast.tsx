"use client";

import { createContext, useCallback, useContext, useState, useRef, ReactNode } from "react";
import { CheckCircle, XCircle, AlertCircle, Info, X } from "lucide-react";

type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return { toast: () => {} };
  }
  return ctx;
}

const ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertCircle,
  info: Info,
};

const COLORS: Record<ToastType, string> = {
  success: "border-green-500/50 bg-green-50 text-green-700",
  error: "border-red-500/50 bg-red-50 text-red-700",
  warning: "border-yellow-500/50 bg-yellow-50 text-yellow-700",
  info: "border-blue-500/50 bg-blue-50 text-blue-700",
};

const ROLES: Record<ToastType, string> = {
  success: "status",
  error: "alert",
  warning: "alert",
  info: "status",
};

const TIMEOUTS: Record<ToastType, number> = {
  success: 4000,
  error: 6000,
  warning: 5000,
  info: 4000,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    if (timers.current[id]) {
      clearTimeout(timers.current[id]);
      delete timers.current[id];
    }
  }, []);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, type, message }]);
    timers.current[id] = setTimeout(() => dismiss(id), TIMEOUTS[type]);
  }, [dismiss]);

  const pauseTimer = (id: number) => {
    if (timers.current[id]) {
      clearTimeout(timers.current[id]);
    }
  };

  const resumeTimer = (id: number, type: ToastType) => {
    timers.current[id] = setTimeout(() => dismiss(id), TIMEOUTS[type]);
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {toasts.map((t) => {
          const Icon = ICONS[t.type];
          return (
            <div
              key={t.id}
              role={ROLES[t.type]}
              aria-live={t.type === "error" || t.type === "warning" ? "assertive" : "polite"}
              onMouseEnter={() => pauseTimer(t.id)}
              onMouseLeave={() => resumeTimer(t.id, t.type)}
              className={`flex items-center gap-3 rounded-md border px-4 py-3 text-sm shadow-lg ${COLORS[t.type]}`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                aria-label="閉じる"
                className="ml-2 shrink-0 opacity-60 hover:opacity-100"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
