"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Pagination } from "@/components/pagination";
import { ScrollText, Download, Search, RefreshCw, X, Loader2 } from "lucide-react";

interface AuditLog {
  log_id: string;
  user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  method: string;
  path: string;
  status_code: number;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

interface AuditLogList {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
}

const ACTION_LABELS: Record<string, string> = {
  get: "取得",
  post: "作成",
  put: "更新",
  patch: "部分更新",
  delete: "削除",
};

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-gray-100 text-gray-700",
  POST: "bg-green-100 text-green-700",
  PUT: "bg-blue-100 text-blue-700",
  PATCH: "bg-yellow-100 text-yellow-700",
  DELETE: "bg-red-100 text-red-700",
};

export default function AuditLogPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canView = user?.permissions.includes("report:read") ?? false;

  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 50;
  const [actionFilter, setActionFilter] = useState("");
  const [resourceFilter, setResourceFilter] = useState("");
  const [exportLoading, setExportLoading] = useState(false);

  const fetchLogs = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {
        company_id: companyId,
        page: String(page),
        page_size: String(pageSize),
      };
      if (actionFilter) params.action = actionFilter;
      if (resourceFilter) params.resource_type = resourceFilter;
      const data = await apiGet<AuditLogList>("/audit/logs", params);
      setLogs(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && canView) fetchLogs();
  }, [companyId, page, actionFilter, resourceFilter]);

  const handleExport = async () => {
    if (!companyId) return;
    setExportLoading(true);
    try {
      const token = localStorage.getItem("token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/audit/export?company_id=${companyId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("エクスポートに失敗しました");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_export_${new Date().toISOString().split("T")[0]}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "エクスポートに失敗しました");
    } finally {
      setExportLoading(false);
    }
  };

  if (!canView) {
    return (
      <PageLayout>
        <div className="mb-6 flex items-center gap-3">
          <ScrollText className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">操作証跡ログ</h1>
        </div>
        <div className="rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          この機能を利用する権限がありません。
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ScrollText className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">操作証跡ログ</h1>
        </div>
        <button
          onClick={handleExport}
          disabled={!companyId || exportLoading}
          className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {exportLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {exportLoading ? "出力中..." : "監査データエクスポート"}
        </button>
      </div>

      {!companyId && (
        <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          サイドバーで会社を選択してください。
        </div>
      )}

      {error && (
        <div role="alert" className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={actionFilter}
          onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
          className="rounded-md border px-2 py-1.5 text-sm"
        >
          <option value="">全アクション</option>
          <option value="get">取得</option>
          <option value="post">作成</option>
          <option value="put">更新</option>
          <option value="patch">部分更新</option>
          <option value="delete">削除</option>
        </select>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="リソース種別でフィルタ..."
            value={resourceFilter}
            onChange={(e) => { setResourceFilter(e.target.value); setPage(1); }}
            className="w-48 rounded-md border py-1.5 pl-8 pr-7 text-sm"
          />
          {resourceFilter && (
            <button
              onClick={() => { setResourceFilter(""); setPage(1); }}
              aria-label="クリア"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-accent"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
        {total > 0 && <span className="text-xs text-muted-foreground">{total}件</span>}
        <button
          onClick={fetchLogs}
          disabled={loading || !companyId}
          className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          更新
        </button>
      </div>

      {loading ? (
        <SkeletonTable rows={5} columns={7} />
      ) : logs.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium">日時</th>
                <th className="px-4 py-3 text-center font-medium">メソッド</th>
                <th className="px-4 py-3 text-left font-medium">アクション</th>
                <th className="px-4 py-3 text-left font-medium">リソース</th>
                <th className="px-4 py-3 text-left font-medium">パス</th>
                <th className="px-4 py-3 text-center font-medium">ステータス</th>
                <th className="px-4 py-3 text-left font-medium">IP</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.log_id} className="border-t hover:bg-muted/30">
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {new Date(log.created_at).toLocaleString("ja-JP")}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded px-2 py-0.5 text-xs font-mono ${METHOD_COLORS[log.method] || "bg-gray-100 text-gray-700"}`}>
                      {log.method}
                    </span>
                  </td>
                  <td className="px-4 py-3">{ACTION_LABELS[log.action] || log.action}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {log.resource_type}
                    {log.resource_id && ` / ${log.resource_id.substring(0, 8)}...`}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{log.path}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded px-2 py-0.5 text-xs ${log.status_code < 400 ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {log.status_code}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{log.ip_address || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <ScrollText className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "操作証跡ログがありません。" : "会社を選択してください。"}
          </p>
        </div>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
    </PageLayout>
  );
}
