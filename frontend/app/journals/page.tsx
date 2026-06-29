"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPostMultipart } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { Receipt, Filter, Search, Download, Upload, BookOpen, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { SkeletonTable } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { Pagination } from "@/components/pagination";

interface Journal {
  journal_header_id: string;
  journal_number: string;
  transaction_date: string;
  voucher_type: string;
  summary: string | null;
  approval_status: string;
  is_voided: boolean;
  created_at: string;
}

interface JournalList {
  items: Journal[];
  total: number;
  page: number;
  page_size: number;
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

export default function JournalsListPage() {
  const { companyId } = useCompany();
  const { toast } = useToast();
  const [data, setData] = useState<JournalList | null>(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [importLoading, setImportLoading] = useState(false);

  const fetchJournals = async () => {
    if (!companyId) {
      setError("サイドバーで会社IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const params: Record<string, string> = {
        company_id: companyId,
        page: String(page),
        page_size: "20",
      };
      if (statusFilter) params.approval_status = statusFilter;
      const data = await apiGet<JournalList>("/journals", params);
      setData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setData(null);
    setPage(1);
  }, [companyId, statusFilter]);

  useEffect(() => {
    if (companyId) fetchJournals();
  }, [companyId, page, statusFilter]);

  const filteredItems = data
    ? data.items.filter((j) => {
        const matchesSearch =
          !searchQuery ||
          j.journal_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (j.summary || "").toLowerCase().includes(searchQuery.toLowerCase());
        return matchesSearch;
      })
    : [];

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  const handleExportCSV = async () => {
    if (!companyId) return;
    const today = new Date().toISOString().split("T")[0];
    const startDate = `${new Date().getFullYear()}-01-01`;
    try {
      const csv = await apiGet<string>("/journals/export/csv", {
        company_id: companyId,
        start_date: startDate,
        end_date: today,
      });
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `journals_${startDate}_${today}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("仕訳CSVを出力しました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "CSV出力に失敗しました", "error");
    }
  };

  const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!companyId || !e.target.files?.[0]) return;
    setImportLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", e.target.files[0]);
      const result = await apiPostMultipart<{ imported: number; errors: string[]; total_rows: number }>(
        `/journals/import/csv`,
        { company_id: companyId },
        formData
      );
      toast(`${result.imported}件インポートしました${result.errors.length > 0 ? `（${result.errors.length}件エラー）` : ""}`, result.errors.length > 0 ? "warning" : "success");
      if (result.errors.length > 0) {
        console.error("Import errors:", result.errors);
      }
      await fetchJournals();
    } catch (err) {
      toast(err instanceof Error ? err.message : "CSVインポートに失敗しました", "error");
    } finally {
      setImportLoading(false);
      e.target.value = "";
    }
  };

  return (
    <PageLayout>
        <div className="mb-6 flex items-center gap-3">
          <Receipt className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">仕訳一覧</h1>
        </div>

        <div className="mb-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="仕訳番号・摘要で検索..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-48 rounded-md border py-1.5 pl-8 pr-3 text-sm"
              />
            </div>
            <Filter className="h-4 w-4 text-muted-foreground" />
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              className="rounded-md border px-2 py-1.5 text-sm"
            >
              <option value="">全ステータス</option>
              <option value="draft">下書き</option>
              <option value="submitted">承認待ち</option>
              <option value="approved">承認済</option>
              <option value="posted">転記済</option>
              <option value="rejected">差し戻し</option>
            </select>
            {data && <span className="text-xs text-muted-foreground">{filteredItems.length}/{data.total}件</span>}
          </div>
          <button
            onClick={() => { setPage(1); fetchJournals(); }}
            disabled={loading || !companyId}
            className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "取得中..." : "更新"}
          </button>
        </div>

        <div className="mb-6 flex items-center gap-2">
          <Link
            href="/journals/new"
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            <Plus className="h-4 w-4" />
            新規仕訳入力
          </Link>
          <button
            onClick={handleExportCSV}
            disabled={!companyId}
            className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            仕訳CSV出力
          </button>
          <label className={`flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium ${importLoading || !companyId ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}>
            <Upload className="h-4 w-4" />
            {importLoading ? "インポート中..." : "仕訳CSVインポート"}
            <input type="file" accept=".csv" onChange={handleImportCSV} className="hidden" disabled={importLoading || !companyId} />
          </label>
          <Link
            href="/journals/general-ledger"
            className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium"
          >
            <BookOpen className="h-4 w-4" />
            総勘定元帳
          </Link>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading && !data && (
          <SkeletonTable rows={5} columns={5} />
        )}

        {data && (
          <>
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">仕訳番号</th>
                    <th className="px-4 py-3 text-left font-medium">取引日</th>
                    <th className="px-4 py-3 text-left font-medium">摘要</th>
                    <th className="px-4 py-3 text-left font-medium">ステータス</th>
                    <th className="px-4 py-3 text-left font-medium">無効化</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((j) => (
                    <tr key={j.journal_header_id} className="border-t hover:bg-muted/30 cursor-pointer">
                      <td className="px-4 py-3 font-mono">
                        <Link href={`/journals/${j.journal_header_id}`} className="text-primary hover:underline">
                          {j.journal_number}
                        </Link>
                      </td>
                      <td className="px-4 py-3">{j.transaction_date}</td>
                      <td className="px-4 py-3">{j.summary || "-"}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[j.approval_status] || "bg-gray-100"}`}>
                          {STATUS_LABELS[j.approval_status] || j.approval_status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {j.is_voided ? (
                          <span className="text-xs text-red-600">無効</span>
                        ) : (
                          <span className="text-xs text-green-600">有効</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {filteredItems.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                        該当する仕訳がありません
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <Pagination page={page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
          </>
        )}
    </PageLayout>
  );
}
