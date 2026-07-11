"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiPatch } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { ShieldAlert, RefreshCw, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface Detection {
  audit_detection_log_id: string;
  journal_header_id: string | null;
  risk_level: string;
  category: string;
  message: string;
  details: Record<string, unknown> | null;
  status: string;
  reviewed_at: string | null;
  created_at: string;
}

const RISK_LABELS: Record<string, string> = { high: "高", medium: "中", low: "低" };
const RISK_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-gray-100 text-gray-600",
};
const CATEGORY_LABELS: Record<string, string> = {
  high_amount: "高額仕訳",
  round_amount: "丸め金額",
  weekend_entry: "休日起票",
  backdated: "バックデート",
  sod_conflict: "職務分掌違反",
  duplicate: "重複の疑い",
  benford_deviation: "Benford分布乖離",
  period_end_concentration: "期末集中起票",
};
const STATUS_LABELS: Record<string, string> = { open: "未確認", confirmed: "確認済", dismissed: "却下" };

export default function AuditDetectionPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canReview = user?.permissions.includes("audit:review") ?? false;

  const [detections, setDetections] = useState<Detection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [scanning, setScanning] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [riskFilter, setRiskFilter] = useState("");

  const fetchDetections = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId, limit: "200" };
      if (statusFilter) params.status = statusFilter;
      if (riskFilter) params.risk_level = riskFilter;
      const data = await apiGet<Detection[]>("/audit-detection/detections", params);
      setDetections(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && canReview) fetchDetections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, statusFilter, riskFilter]);

  const handleScan = async () => {
    if (!companyId) return;
    setScanning(true);
    setError("");
    setNotice("");
    try {
      const result = await apiPost<{ scanned: number; detections_created: number }>(
        `/audit-detection/scan?company_id=${encodeURIComponent(companyId)}`,
        {}
      );
      setNotice(`${result.scanned}件の仕訳をスキャンし、${result.detections_created}件のリスクを新規検知しました。`);
      await fetchDetections();
    } catch (err) {
      setError(err instanceof Error ? err.message : "スキャンに失敗しました");
    } finally {
      setScanning(false);
    }
  };

  const handleStatus = async (id: string, status: string) => {
    if (!companyId) return;
    setError("");
    try {
      await apiPatch<Detection>(
        `/audit-detection/detections/${id}?company_id=${encodeURIComponent(companyId)}`,
        { status }
      );
      await fetchDetections();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新に失敗しました");
    }
  };

  if (!canReview) {
    return (
      <PageLayout title="監査・リスク検知">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（audit:review が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="監査・リスク検知">
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-muted-foreground">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
            <p className="text-sm">仕訳をスキャンし、高額・丸め金額・休日起票・職務分掌違反などのリスクを検知します。</p>
          </div>
          <button
            type="button"
            onClick={handleScan}
            disabled={scanning}
            className="ml-auto inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {scanning ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
            スキャン実行
          </button>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            {notice}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="status-filter" className="text-sm font-medium">状態:</label>
          <select id="status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
            <option value="">すべて</option>
            <option value="open">未確認</option>
            <option value="confirmed">確認済</option>
            <option value="dismissed">却下</option>
          </select>
          <label htmlFor="risk-filter" className="text-sm font-medium">リスク:</label>
          <select id="risk-filter" value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
            <option value="">すべて</option>
            <option value="high">高</option>
            <option value="medium">中</option>
            <option value="low">低</option>
          </select>
        </div>

        {loading ? (
          <SkeletonTable rows={6} columns={5} />
        ) : detections.length === 0 ? (
          <p className="text-sm text-muted-foreground">検知結果がありません。スキャンを実行してください。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">検知されたリスクの一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-center font-medium">リスク</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">カテゴリ</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">内容</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">状態</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {detections.map((d) => (
                  <tr key={d.audit_detection_log_id} className="border-t align-top">
                    <td className="px-3 py-2 text-center">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${RISK_STYLES[d.risk_level] ?? ""}`}>
                        {RISK_LABELS[d.risk_level] ?? d.risk_level}
                      </span>
                    </td>
                    <td className="px-3 py-2">{CATEGORY_LABELS[d.category] ?? d.category}</td>
                    <td className="px-3 py-2">{d.message}</td>
                    <td className="px-3 py-2 text-center">{STATUS_LABELS[d.status] ?? d.status}</td>
                    <td className="px-3 py-2 text-right">
                      {d.status === "open" && (
                        <div className="inline-flex gap-1">
                          <button
                            type="button"
                            onClick={() => handleStatus(d.audit_detection_log_id, "confirmed")}
                            className="inline-flex items-center gap-1 rounded-md border border-green-300 px-2 py-1 text-xs text-green-700"
                            aria-label={`${CATEGORY_LABELS[d.category] ?? d.category} を確認済にする`}
                          >
                            <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> 確認
                          </button>
                          <button
                            type="button"
                            onClick={() => handleStatus(d.audit_detection_log_id, "dismissed")}
                            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground"
                            aria-label={`${CATEGORY_LABELS[d.category] ?? d.category} を却下する`}
                          >
                            <XCircle className="h-3 w-3" aria-hidden="true" /> 却下
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
