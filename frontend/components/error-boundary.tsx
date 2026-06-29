"use client";

import { Component, ReactNode } from "react";
import { AlertCircle } from "lucide-react";

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
        <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/50 bg-destructive/5 p-12">
          <AlertCircle className="mb-3 h-10 w-10 text-destructive" />
          <p className="text-sm font-medium text-destructive">エラーが発生しました</p>
          <p className="mt-1 text-xs text-muted-foreground">{this.state.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, message: "" })}
            className="mt-4 rounded-md border px-4 py-2 text-sm hover:bg-accent"
          >
            再試行
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
