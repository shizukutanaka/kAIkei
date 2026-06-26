"use client";

import { useState } from "react";
import Sidebar from "@/components/sidebar";
import { CheckCircle, XCircle, Send, FileCheck, Clock, History } from "lucide-react";

interface ApprovalLog {
  log_id: string;
  journal_header_id: string;
  action: string;
  from_status: string;
  to_status: string;
  actor_id: string;
  comment: string | null;
  created_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  draft: "下書き",
  submitted: "承認待ち",
  approved: "承認済",
  posted: "転記済",
  rejected: "差し戻し",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  submitted: "bg-yellow-100 text-yellow-700",
  approved: "bg-green-100 text-green-700",
  posted: "bg-blue-100 text-blue-700",
  rejected: "bg-red-100 text-red-700",
};

const ACTION_ICONS: Record<string, typeof Send> = {
  submit: Send,
  approve: CheckCircle,
  reject: XCircle,
  post: FileCheck,
};

export default function ApprovalsPage() {
  const [journalId, setJournalId] = useState("");
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<ApprovalLog[] | null>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const handleAction = async (action: string) => {
    if (!journalId) {
      setError("仕訳IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const body: Record<string, unknown> = { journal_header_id: journalId };
      if (comment && (action === "approve" || action === "reject")) {
        body.comment = comment;
      }

      const response = await fetch(`http://localhost:8000/api/v1/approvals/${action}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "操作に失敗しました");
      }
      setResult(data);
      await fetchHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    if (!journalId) return;
    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/approvals/history/${journalId}`,
        { headers }
      );
      if (response.ok) {
        setHistory(await response.json());
      }
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <div className="mb-6 flex items-center gap-3">
          <FileCheck className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">承認ワークフロー</h1>
        </div>

        <div className="mb-6 rounded-lg border bg-card p-6">
          <h2 className="mb-4 text-lg font-semibold">仕訳ID</h2>
          <input
            type="text"
            value={journalId}
            onChange={(e) => setJournalId(e.target.value)}
            placeholder="journal_header_id (UUID)"
            className="mb-4 w-full rounded-md border px-3 py-2 text-sm"
          />

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium">コメント（承認・差し戻し時）</label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="承認/差し戻しのコメント"
              className="w-full rounded-md border px-3 py-2 text-sm"
              rows={2}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => handleAction("submit")}
              disabled={loading}
              className="flex items-center gap-2 rounded-md bg-yellow-600 px-4 py-2 text-sm font-medium text-white hover:bg-yellow-700 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
              承認に提出
            </button>
            <button
              onClick={() => handleAction("approve")}
              disabled={loading}
              className="flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              <CheckCircle className="h-4 w-4" />
              承認
            </button>
            <button
              onClick={() => handleAction("reject")}
              disabled={loading}
              className="flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              <XCircle className="h-4 w-4" />
              差し戻し
            </button>
            <button
              onClick={() => handleAction("post")}
              disabled={loading}
              className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <FileCheck className="h-4 w-4" />
              転記
            </button>
            <button
              onClick={fetchHistory}
              disabled={loading || !journalId}
              className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
            >
              <History className="h-4 w-4" />
              履歴取得
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {result && (
          <div className="mb-4 rounded-lg border bg-card p-4">
            <div className="flex items-center gap-2">
              <span className={`rounded px-2 py-1 text-xs font-medium ${STATUS_COLORS[result.approval_status as string] || "bg-gray-100"}`}>
                {STATUS_LABELS[result.approval_status as string] || result.approval_status}
              </span>
              <span className="text-sm text-muted-foreground">{result.message as string}</span>
            </div>
          </div>
        )}

        {history && history.length > 0 && (
          <div className="rounded-lg border bg-card p-4">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <Clock className="h-4 w-4" />
              承認履歴
            </h3>
            <div className="space-y-2">
              {history.map((log) => {
                const Icon = ACTION_ICONS[log.action] || Clock;
                return (
                  <div key={log.log_id} className="flex items-start gap-3 border-b pb-2 last:border-0">
                    <Icon className="mt-0.5 h-4 w-4 text-muted-foreground" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{log.action}</span>
                        <span className="text-xs text-muted-foreground">
                          {STATUS_LABELS[log.from_status] || log.from_status} → {STATUS_LABELS[log.to_status] || log.to_status}
                        </span>
                      </div>
                      {log.comment && (
                        <p className="text-xs text-muted-foreground">{log.comment}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {new Date(log.created_at).toLocaleString("ja-JP")}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {history && history.length === 0 && (
          <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
            承認履歴がありません
          </div>
        )}
      </main>
    </div>
  );
}
