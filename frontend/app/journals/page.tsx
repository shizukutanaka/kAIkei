"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import { Receipt, ChevronLeft, ChevronRight } from "lucide-react";

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
  const [companyId, setCompanyId] = useState("");
  const [data, setData] = useState<JournalList | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";

  const fetchJournals = async () => {
    if (!companyId) {
      setError("会社IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/journals?company_id=${companyId}&page=${page}&page_size=20`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (response.ok) {
        setData(await response.json());
      } else {
        const err = await response.json();
        setError(err.detail || "取得に失敗しました");
      }
    } catch {
      setError("通信エラー");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) fetchJournals();
  }, [page]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <div className="mb-6 flex items-center gap-3">
          <Receipt className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">仕訳一覧</h1>
        </div>

        <div className="mb-6 flex items-center gap-4 rounded-lg border bg-card p-4">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-medium">会社ID</label>
            <input
              type="text"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              placeholder="UUID"
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          </div>
          <button
            onClick={() => { setPage(1); fetchJournals(); }}
            disabled={loading}
            className="mt-5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {loading ? "取得中..." : "検索"}
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
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
                  {data.items.map((j) => (
                    <tr key={j.journal_header_id} className="border-t hover:bg-muted/30">
                      <td className="px-4 py-3 font-mono">{j.journal_number}</td>
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
                  {data.items.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                        仕訳がありません
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                {data.total}件中 {((data.page - 1) * data.page_size) + 1}-{Math.min(data.page * data.page_size, data.total)}件
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page === 1}
                  className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  <ChevronLeft className="h-4 w-4" />
                  前へ
                </button>
                <span className="text-sm">{page} / {totalPages || 1}</span>
                <button
                  onClick={() => setPage(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  次へ
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
