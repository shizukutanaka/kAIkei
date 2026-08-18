"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Sparkles, RefreshCw } from "lucide-react";

interface InferenceLog {
  ai_inference_log_id: string;
  source_type: string;
  input_summary: string | null;
  confidence: string;
  provider: string | null;
  applied: boolean;
  correction_diff: Record<string, unknown> | null;
  created_at: string;
}

interface Stats {
  total: number;
  applied: number;
  acceptance_rate: number;
  corrected: number;
  correction_rate: number;
  avg_confidence: number;
}

const SOURCE_LABELS: Record<string, string> = {
  journal_suggest: "仕訳提案",
  tax_predict: "税区分予測",
  anomaly: "異常検知",
};

function confidenceBand(c: number): { label: string; cls: string } {
  if (c >= 0.9) return { label: "高", cls: "bg-green-100 text-green-700" };
  if (c >= 0.7) return { label: "中", cls: "bg-yellow-100 text-yellow-700" };
  return { label: "低", cls: "bg-red-100 text-red-700" };
}

export default function AiInferenceLogsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canReview = user?.permissions.includes("ai:review") ?? false;

  const [logs, setLogs] = useState<InferenceLog[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [appliedFilter, setAppliedFilter] = useState("");

  const fetchData = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId, limit: "200" };
      if (sourceFilter) params.source_type = sourceFilter;
      if (appliedFilter) params.applied = appliedFilter;
      const [logData, statsData] = await Promise.all([
        apiGet<InferenceLog[]>("/ai-inference-logs", params),
        apiGet<Stats>("/ai-inference-logs/stats", { company_id: companyId }),
      ]);
      setLogs(logData);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && canReview) fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, sourceFilter, appliedFilter, canReview]);

  if (!canReview) {
    return (
      <PageLayout title="AI推論証跡">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（ai:review が必要です）。</p>
      </PageLayout>
    );
  }

  const statCards = stats
    ? [
        { label: "推論件数", value: String(stats.total) },
        { label: "適用率", value: `${Math.round(stats.acceptance_rate * 100)}%` },
        { label: "修正率", value: `${Math.round(stats.correction_rate * 100)}%` },
        { label: "平均信頼度", value: stats.avg_confidence.toFixed(2) },
      ]
    : [];

  return (
    <PageLayout title="AI推論証跡">
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
            <p className="text-sm">AI推論の提案・信頼度・適用状況・修正差分を監査します（説明責任）。</p>
          </div>
          <button type="button" onClick={fetchData} className="ml-auto inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm" aria-label="再読み込み">
            <RefreshCw className="h-4 w-4" aria-hidden="true" /> 更新
          </button>
        </div>

        {error && <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

        {stats && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {statCards.map((c) => (
              <div key={c.label} className="rounded-lg border p-4">
                <div className="text-xs text-muted-foreground">{c.label}</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">{c.value}</div>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="source-filter" className="text-sm font-medium">推論元:</label>
          <select id="source-filter" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
            <option value="">すべて</option>
            <option value="journal_suggest">仕訳提案</option>
            <option value="tax_predict">税区分予測</option>
            <option value="anomaly">異常検知</option>
          </select>
          <label htmlFor="applied-filter" className="text-sm font-medium">適用:</label>
          <select id="applied-filter" value={appliedFilter} onChange={(e) => setAppliedFilter(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
            <option value="">すべて</option>
            <option value="true">適用済み</option>
            <option value="false">未適用</option>
          </select>
        </div>

        {loading ? (
          <SkeletonTable rows={6} columns={5} />
        ) : logs.length === 0 ? (
          <p className="text-sm text-muted-foreground">推論証跡がありません。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">AI推論証跡の一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">推論元</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">概要</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">信頼度</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">適用</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">プロバイダ</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const band = confidenceBand(Number(log.confidence));
                  return (
                    <tr key={log.ai_inference_log_id} className="border-t">
                      <td className="px-3 py-2">{SOURCE_LABELS[log.source_type] ?? log.source_type}</td>
                      <td className="px-3 py-2 text-muted-foreground">{log.input_summary || "-"}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${band.cls}`}>
                          {band.label} ({Number(log.confidence).toFixed(2)})
                        </span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        {log.applied ? (
                          <span className="text-xs">
                            適用済{log.correction_diff ? "（修正あり）" : ""}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">未適用</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs">{log.provider || "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
