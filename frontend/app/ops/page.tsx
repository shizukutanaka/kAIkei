"use client";

import { useState, useEffect, useCallback } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonCard } from "@/components/skeleton";
import { Activity, RefreshCw, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

interface HealthSummary {
  total: number;
  failed: number;
  dead: number;
  failure_rate: number;
  level: string;
}

interface OperationsHealth {
  company_id: string;
  overall_level: string;
  jobs: HealthSummary;
  webhooks: HealthSummary;
  overdue_tasks: number;
}

const LEVEL_STYLE: Record<string, { label: string; cls: string; Icon: typeof CheckCircle2 }> = {
  healthy: { label: "正常", cls: "text-green-700 border-green-500/40 bg-green-50", Icon: CheckCircle2 },
  ok: { label: "正常", cls: "text-green-700 border-green-500/40 bg-green-50", Icon: CheckCircle2 },
  warning: { label: "注意", cls: "text-amber-700 border-amber-500/40 bg-amber-50", Icon: AlertTriangle },
  degraded: { label: "注意", cls: "text-amber-700 border-amber-500/40 bg-amber-50", Icon: AlertTriangle },
  critical: { label: "危険", cls: "text-destructive border-destructive/40 bg-destructive/10", Icon: XCircle },
};

function levelStyle(level: string) {
  return LEVEL_STYLE[level] ?? { label: level, cls: "text-muted-foreground border-muted", Icon: Activity };
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function HealthCard({ title, summary }: { title: string; summary: HealthSummary }) {
  const s = levelStyle(summary.level);
  return (
    <div className={`rounded-lg border p-4 ${s.cls}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="inline-flex items-center gap-1 text-xs font-medium"><s.Icon className="h-4 w-4" aria-hidden="true" /> {s.label}</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm text-foreground">
        <div><dt className="text-xs text-muted-foreground">総数</dt><dd className="tabular-nums">{summary.total}</dd></div>
        <div><dt className="text-xs text-muted-foreground">失敗率</dt><dd className="tabular-nums">{pct(summary.failure_rate)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">失敗(再試行)</dt><dd className="tabular-nums">{summary.failed}</dd></div>
        <div><dt className="text-xs text-muted-foreground">確定失敗</dt><dd className="tabular-nums">{summary.dead}</dd></div>
      </dl>
    </div>
  );
}

export default function OpsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("master:read") ?? false;

  const [health, setHealth] = useState<OperationsHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<OperationsHealth>("/ops/health", { company_id: companyId });
      setHealth(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "運用状態の取得に失敗しました");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!canRead) {
    return (
      <PageLayout title="運用モニタリング">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（master:read が必要です）。</p>
      </PageLayout>
    );
  }

  const overall = health ? levelStyle(health.overall_level) : null;

  return (
    <PageLayout title="運用モニタリング">
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Activity className="h-5 w-5" aria-hidden="true" />
            <p className="text-sm">スケジュールジョブ・Webhook配信・期限超過タスクの実行状態を集約表示します。</p>
          </div>
          <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" /> 更新
          </button>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}

        {loading && !health ? (
          <div className="grid gap-4 sm:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}</div>
        ) : health && overall ? (
          <>
            <div className={`flex items-center gap-2 rounded-lg border px-4 py-3 ${overall.cls}`} role="status">
              <overall.Icon className="h-5 w-5" aria-hidden="true" />
              <span className="text-sm font-semibold">総合ステータス: {overall.label}</span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <HealthCard title="スケジュールジョブ" summary={health.jobs} />
              <HealthCard title="Webhook配信" summary={health.webhooks} />
              <div className={`rounded-lg border p-4 ${health.overdue_tasks > 0 ? "text-amber-700 border-amber-500/40 bg-amber-50" : ""}`}>
                <h3 className="text-sm font-semibold">期限超過タスク</h3>
                <p className="mt-3 text-2xl font-semibold tabular-nums">{health.overdue_tasks}</p>
                <p className="text-xs text-muted-foreground">未完了かつ期限を過ぎた月次業務タスク</p>
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">運用状態を取得できませんでした。</p>
        )}
      </div>
    </PageLayout>
  );
}
