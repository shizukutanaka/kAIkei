"use client";

import { Component, ReactNode } from "react";
import { AlertCircle, RotateCcw, Home } from "lucide-react";
import Link from "next/link";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          aria-live="polite"
          className="flex flex-col items-center justify-center rounded-lg border border-destructive/50 bg-destructive/5 p-12"
        >
          <AlertCircle className="mb-3 h-10 w-10 text-destructive" />
          <p className="text-sm font-medium text-destructive">ページの読み込みに失敗しました</p>
          <p className="mt-1 text-xs text-muted-foreground">
            データは保護されています。再試行またはホームに戻ることができます。
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => this.setState({ hasError: false, message: "" })}
              className="flex items-center gap-1.5 rounded-md border px-4 py-2 text-sm hover:bg-accent"
            >
              <RotateCcw className="h-4 w-4" />
              再試行
            </button>
            <Link
              href="/dashboard"
              className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              <Home className="h-4 w-4" />
              ホームへ
            </Link>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
