"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { ArrowLeft, Receipt, Send, CheckCircle, XCircle, FileCheck, Loader2 } from "lucide-react";
import { SkeletonTable } from "@/components/skeleton";

interface JournalLine {
  line_number: number;
  debit_credit: string;
  account_id: string;
  amount: string;
  tax_amount: string;
  description: string | null;
}

interface JournalDetail {
  journal_header_id: string;
  journal_number: string;
  company_id: string;
  transaction_date: string;
  voucher_type: string;
  summary: string | null;
  approval_status: string;
  is_voided: boolean;
  created_by: string;
  created_at: string;
  lines: JournalLine[];
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

export default function JournalDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const { user } = useUser();
  const perms = user?.permissions ?? [];
  const canSubmit = perms.includes("journal:create");
  const canApprove = perms.includes("journal:approve");
  const canPost = perms.includes("journal:post");
  const [journal, setJournal] = useState<JournalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const id = params?.id as string;

  const fetchJournal = async () => {
    try {
      const data = await apiGet<JournalDetail>(`/journals/${id}`);
      setJournal(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
      toast("仕訳の取得に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    fetchJournal();
  }, [id]);

  const handleApprovalAction = async (action: string) => {
    const actionLabels: Record<string, string> = {
      submit: "承認に提出",
      approve: "承認",
      reject: "差戻し",
      post: "転記",
    };
    const ok = await confirm({
      title: actionLabels[action] || action,
      message: `仕訳「${journal?.summary || journal?.journal_number}」を${actionLabels[action]}しますか？`,
      confirmText: actionLabels[action] || action,
      variant: action === "reject" ? "danger" : "default",
    });
    if (!ok) return;
    setActionLoading(true);
    try {
      await apiPost(`/approvals/${action}`, { journal_header_id: id });
      toast(`${action} 完了`, "success");
      await fetchJournal();
    } catch (err) {
      toast(err instanceof Error ? err.message : "操作に失敗しました", "error");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <PageLayout>
        <button
          onClick={() => router.push("/journals")}
          className="mb-4 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          仕訳一覧へ戻る
        </button>
        <div className="mb-6 h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-4">
              <div className="mb-2 h-3 w-16 animate-pulse rounded bg-muted" />
              <div className="h-4 w-24 animate-pulse rounded bg-muted" />
            </div>
          ))}
        </div>
        <SkeletonTable rows={3} columns={6} />
      </PageLayout>
    );
  }

  if (error || !journal) {
    return (
      <PageLayout>
        <button
          onClick={() => router.push("/journals")}
          className="mb-4 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          仕訳一覧へ戻る
        </button>
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error || "仕訳が見つかりません"}
        </div>
      </PageLayout>
    );
  }

  const debitTotal = journal.lines
    .filter((l) => l.debit_credit === "debit")
    .reduce((sum, l) => sum + parseFloat(l.amount), 0);
  const creditTotal = journal.lines
    .filter((l) => l.debit_credit === "credit")
    .reduce((sum, l) => sum + parseFloat(l.amount), 0);

  return (
    <PageLayout>
      <button
        onClick={() => router.push("/journals")}
        className="mb-4 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        仕訳一覧へ戻る
      </button>

      <div className="mb-6 flex items-center gap-3">
        <Receipt className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">仕訳詳細</h1>
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[journal.approval_status] || "bg-gray-100"}`}>
          {STATUS_LABELS[journal.approval_status] || journal.approval_status}
        </span>
        {journal.is_voided && (
          <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">無効</span>
        )}
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-xs text-muted-foreground">仕訳番号</p>
          <p className="font-mono text-sm font-medium">{journal.journal_number}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-xs text-muted-foreground">取引日</p>
          <p className="text-sm font-medium">{journal.transaction_date}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-xs text-muted-foreground">伝票種別</p>
          <p className="text-sm font-medium">{journal.voucher_type}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-xs text-muted-foreground">作成日時</p>
          <p className="text-sm font-medium">{new Date(journal.created_at).toLocaleString("ja-JP")}</p>
        </div>
      </div>

      {journal.summary && (
        <div className="mb-6 rounded-lg border bg-card p-4">
          <p className="text-xs text-muted-foreground">摘要</p>
          <p className="text-sm">{journal.summary}</p>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-4 py-3 text-left font-medium">行</th>
              <th className="px-4 py-3 text-left font-medium">借貸</th>
              <th className="px-4 py-3 text-left font-medium">科目ID</th>
              <th className="px-4 py-3 text-right font-medium">金額</th>
              <th className="px-4 py-3 text-right font-medium">税額</th>
              <th className="px-4 py-3 text-left font-medium">摘要</th>
            </tr>
          </thead>
          <tbody>
            {journal.lines.map((line) => (
              <tr key={line.line_number} className="border-t">
                <td className="px-4 py-3">{line.line_number}</td>
                <td className="px-4 py-3">{line.debit_credit === "debit" ? "借方" : "貸方"}</td>
                <td className="px-4 py-3 font-mono text-xs">{line.account_id}</td>
                <td className="px-4 py-3 text-right">¥{parseFloat(line.amount).toLocaleString()}</td>
                <td className="px-4 py-3 text-right">¥{parseFloat(line.tax_amount).toLocaleString()}</td>
                <td className="px-4 py-3 text-muted-foreground">{line.description || "-"}</td>
              </tr>
            ))}
            <tr className="border-t-2 bg-muted/30 font-bold">
              <td colSpan={3} className="px-4 py-3">合計</td>
              <td className="px-4 py-3 text-right">借方: ¥{debitTotal.toLocaleString()}</td>
              <td className="px-4 py-3 text-right">貸方: ¥{creditTotal.toLocaleString()}</td>
              <td className="px-4 py-3">
                {debitTotal === creditTotal ? (
                  <span className="text-xs text-green-600">貸借一致</span>
                ) : (
                  <span className="text-xs text-red-600">貸借不一致</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {canSubmit && journal.approval_status === "draft" && (
          <button
            onClick={() => handleApprovalAction("submit")}
            disabled={actionLoading}
            className="flex items-center gap-2 rounded-md bg-yellow-600 px-4 py-2 text-sm font-medium text-white hover:bg-yellow-700 disabled:opacity-50"
          >
            {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            承認に提出
          </button>
        )}
        {canApprove && journal.approval_status === "submitted" && (
          <>
            <button
              onClick={() => handleApprovalAction("approve")}
              disabled={actionLoading}
              className="flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
              承認
            </button>
            <button
              onClick={() => handleApprovalAction("reject")}
              disabled={actionLoading}
              className="flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
              差し戻し
            </button>
          </>
        )}
        {canPost && journal.approval_status === "approved" && (
          <button
            onClick={() => handleApprovalAction("post")}
            disabled={actionLoading}
            className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck className="h-4 w-4" />}
            転記
          </button>
        )}
      </div>
    </PageLayout>
  );
}
