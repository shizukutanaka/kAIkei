"use client";

import { createContext, useCallback, useContext, useState, useEffect, useRef, ReactNode } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "default" | "danger";
}

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    return { confirm: () => Promise.resolve(false) };
  }
  return ctx;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{
    options: ConfirmOptions;
    resolve: (value: boolean) => void;
  } | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setState({ options, resolve });
    });
  }, []);

  const handleConfirm = () => {
    state?.resolve(true);
    setState(null);
  };

  const handleCancel = () => {
    state?.resolve(false);
    setState(null);
  };

  useEffect(() => {
    if (!state) {
      if (previousFocus.current) {
        previousFocus.current.focus();
        previousFocus.current = null;
      }
      return;
    }
    previousFocus.current = document.activeElement as HTMLElement;
    const dialog = dialogRef.current;
    if (dialog) {
      const focusable = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length > 0) {
        focusable[0].focus();
      } else {
        dialog.focus();
      }
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { handleCancel(); return; }
      if (e.key === "Enter") { handleConfirm(); return; }
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [state]);

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40"
          onClick={handleCancel}
        >
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            tabIndex={-1}
            className="w-full max-w-sm rounded-lg border bg-popover p-6 shadow-xl outline-none"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-start gap-3">
              {state.options.variant === "danger" && (
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
              )}
              <div className="flex-1">
                <h3 id="confirm-title" className="text-sm font-semibold">
                  {state.options.title || "確認"}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {state.options.message}
                </p>
              </div>
              <button
                onClick={handleCancel}
                className="rounded p-2 hover:bg-accent"
                aria-label="閉じる"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={handleCancel}
                className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
              >
                {state.options.cancelText || "キャンセル"}
              </button>
              <button
                onClick={handleConfirm}
                className={`rounded-md px-4 py-2 text-sm font-medium text-white ${
                  state.options.variant === "danger"
                    ? "bg-destructive hover:bg-destructive/90"
                    : "bg-primary hover:bg-primary/90"
                }`}
              >
                {state.options.confirmText || "確認"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
