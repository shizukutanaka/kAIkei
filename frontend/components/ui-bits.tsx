"use client";

import { ReactNode } from "react";
import { LucideIcon, Loader2, X } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
      <Icon className="mb-3 h-10 w-10 text-muted-foreground" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && (
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

interface ErrorBannerProps {
  message: string;
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="mb-4 flex items-center justify-between rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="ml-2 shrink-0 opacity-60 hover:opacity-100"
          aria-label="エラーを閉じる"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

interface LoadingButtonProps {
  loading: boolean;
  onClick?: () => void;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
}

export function LoadingButton({
  loading,
  onClick,
  children,
  disabled,
  className = "",
  type = "button",
}: LoadingButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={loading || disabled}
      className={`flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50 ${className}`}
    >
      {loading && (
        <Loader2 className="h-4 w-4 animate-spin" />
      )}
      {children}
    </button>
  );
}
