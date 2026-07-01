"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { CheckCircle, XCircle, Send, FileCheck, Clock, History, Search, RefreshCw, Loader2 } from "lucide-react";
import { SkeletonTable } from "@/components/skeleton";

interface Journal {
  journal_header_id: string;
  journal_number: string;
  transaction_date: string;
  summary: string | null;
  approval_status: string;
  voucher_type: string;
  total_amount: number;
}

interface JournalList {
  items: Journal[];
  total: number;
  page: number;
  page_size: number;
}

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
  const { user } = useUser();
  const { companyId } = useCompany();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const perms = user?.permissions ?? [];
  const canSubmit = perms.includes("journal:create");
  const canApprove = perms.includes("journal:approve");
  const canPost = perms.includes("journal:post");

  const [journals, setJournals] = useState<Journal[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [comment, setComment] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<ApprovalLog[] | null>(null);
  const [statusFilter, setStatusFilter] = useState("submitted");

  const fetchJournals = async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const params: Record<string, string> = {
        company_id: companyId,
        page: "1",
        page_size: "50",
      };
      if (statusFilter) params.approval_status = statusFilter;
      const data = await apiGet<JournalList>("/journals", params);
      setJournals(data.items);
    } catch {
      setJournals([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJournals();
  }, [companyId, statusFilter]);

  const selectedJournal = journals.find((j) => j.journal_header_id === selectedId);

  const handleSelect = (id: string) => {
    setSelectedId(id);
    setResult(null);
    setHistory(null);
    setComment("");
  };

  useEffect(() => {
    if (selectedId) fetchHistory();
  }, [selectedId]);

  const fetchHistory = async () => {
    if (!selectedId) return;
    try {
      const logs = await apiGet<ApprovalLog[]>(`/approvals/history/${selectedId}`);
      setHistory(logs);
    } catch {
      setHistory([]);
    }
  };

  const handleAction = async (action: string) => {
    if (!selectedId) {
      toast("仕訳を選択してください", "warning");
      return;
    }

    if (action === "approve" || action === "reject" || action === "post") {
      const actionLabels: Record<string, string> = {
        approve: "承認",
        reject: "差し戻し",
        post: "転記",
      };
      const ok = await confirm({
        title: actionLabels[action],
        message: `仕訳 ${selectedJournal?.journal_number || ""} を${actionLabels[action]}しますか？`,
        confirmText: actionLabels[action],
        variant: action === "reject" ? "danger" : "default",
      });
      if (!ok) return;
    }

    setLoading(true);
    setResult(null);

    try {
      const body: Record<string, unknown> = { journal_header_id: selectedId };
      if (comment && (action === "approve" || action === "reject")) {
        body.comment = comment;
      }
      const data = await apiPost<Record<string, unknown>>(`/approvals/${action}`, body);
      setResult(data);
      toast(`${action} 完了`, "success");
      await fetchHistory();
      await fetchJournals();
    } catch (err) {
      toast(err instanceof Error ? err.message : "操作に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout title="承認ワークフロー">
        <div className="mb-6 flex items-center gap-3">
          <FileCheck className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">承認ワークフロー</h1>
        </div>

        {!companyId && (
          <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
            サイドバーで会社を選択してください。
          </div>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setSelectedId(""); }}
            className="rounded-md border px-2 py-1.5 text-sm"
          >
            <option value="submitted">承認待ち</option>
            <option value="draft">下書き</option>
            <option value="approved">承認済</option>
            <option value="rejected">差し戻し</option>
            <option value="posted">転記済</option>
            <option value="">全ステータス</option>
          </select>
          <span className="text-xs text-muted-foreground">{journals.length}件</span>
          <button
            onClick={fetchJournals}
            disabled={loading || !companyId}
            className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            更新
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-4">
            <h2 className="mb-3 text-sm font-semibold">仕訳一覧</h2>
            {loading && journals.length === 0 ? (
              <SkeletonTable rows={4} columns={3} />
            ) : journals.length > 0 ? (
              <div className="max-h-96 space-y-1 overflow-y-auto">
                {journals.map((j) => (
                  <button
                    key={j.journal_header_id}
                    onClick={() => handleSelect(j.journal_header_id)}
                    className={`w-full rounded-md border p-3 text-left text-sm transition-colors ${
                      selectedId === j.journal_header_id
                        ? "border-primary bg-primary/5"
                        : "hover:bg-muted/30"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{j.journal_number}</span>
                      <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[j.approval_status] || "bg-gray-100 text-gray-700"}`}>
                        {STATUS_LABELS[j.approval_status] || j.approval_status}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                      <span>{j.transaction_date}</span>
                      <span>{j.summary || "—"}</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8">
                <Search className="mb-2 h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {companyId ? "該当する仕訳がありません" : "会社を選択してください"}
                </p>
              </div>
            )}
          </div>

          <div className="space-y-4">
            {selectedJournal ? (
              <div className="rounded-lg border bg-card p-6">
                <h2 className="mb-4 text-lg font-semibold">
                  仕訳詳細: {selectedJournal.journal_number}
                </h2>
                <div className="mb-4 grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">取引日</p>
                    <p className="text-sm font-medium">{selectedJournal.transaction_date}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">ステータス</p>
                    <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[selectedJournal.approval_status] || "bg-gray-100 text-gray-700"}`}>
                      {STATUS_LABELS[selectedJournal.approval_status] || selectedJournal.approval_status}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <p className="text-xs text-muted-foreground">摘要</p>
                    <p className="text-sm font-medium">{selectedJournal.summary || "—"}</p>
                  </div>
                </div>

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
                  {canSubmit && selectedJournal.approval_status === "draft" && (
                    <button
                      onClick={() => handleAction("submit")}
                      disabled={loading}
                      className="flex items-center gap-2 rounded-md bg-yellow-600 px-4 py-2 text-sm font-medium text-white hover:bg-yellow-700 disabled:opacity-50"
                    >
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      承認に提出
                    </button>
                  )}
                  {canApprove && selectedJournal.approval_status === "submitted" && (
                    <>
                      <button
                        onClick={() => handleAction("approve")}
                        disabled={loading}
                        className="flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                      >
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                        承認
                      </button>
                      <button
                        onClick={() => handleAction("reject")}
                        disabled={loading}
                        className="flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                      >
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                        差し戻し
                      </button>
                    </>
                  )}
                  {canPost && selectedJournal.approval_status === "approved" && (
                    <button
                      onClick={() => handleAction("post")}
                      disabled={loading}
                      className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck className="h-4 w-4" />}
                      転記
                    </button>
                  )}
                  <button
                    onClick={fetchHistory}
                    disabled={loading}
                    className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
                  >
                    <History className="h-4 w-4" />
                    履歴取得
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
                <FileCheck className="mb-3 h-10 w-10 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">左のリストから仕訳を選択してください</p>
              </div>
            )}

            {result && (
              <div className="rounded-lg border bg-card p-4">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-2 py-1 text-xs font-medium ${STATUS_COLORS[String(result.approval_status ?? "")] || "bg-gray-100"}`}>
                    {STATUS_LABELS[String(result.approval_status ?? "")] || String(result.approval_status ?? "")}
                  </span>
                  <span className="text-sm text-muted-foreground">{String(result.message ?? "")}</span>
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
          </div>
        </div>
    </PageLayout>
  );
}
