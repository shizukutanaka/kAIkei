"use client";

import { useState, useEffect, useCallback } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { CalendarClock, Plus, Play, Zap, Loader2, CheckCircle2, X } from "lucide-react";

interface ScheduledJob {
  scheduled_job_id: string;
  company_id: string;
  job_type: string;
  frequency: string;
  run_hour: number;
  run_day: number | null;
  priority: number;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

interface JobExecution {
  job_execution_id: string;
  scheduled_job_id: string | null;
  job_type: string;
  status: string;
  priority: number;
  attempt_count: number;
  scheduled_for: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  created_at: string;
}

const FREQUENCIES = [
  { value: "daily", label: "毎日" },
  { value: "weekly", label: "毎週" },
  { value: "monthly", label: "毎月" },
];

const STATUS_LABELS: Record<string, string> = {
  pending: "待機中",
  running: "実行中",
  succeeded: "成功",
  failed_retry: "再試行待ち",
  dead: "失敗",
};

function fmtDateTime(v: string | null): string {
  if (!v) return "-";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString("ja-JP");
}

export default function JobsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("master:read") ?? false;
  const canManage = user?.permissions.includes("master:create") ?? false;

  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [executions, setExecutions] = useState<JobExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [jobType, setJobType] = useState("");
  const [frequency, setFrequency] = useState("monthly");
  const [runHour, setRunHour] = useState("2");
  const [runDay, setRunDay] = useState("1");
  const [priority, setPriority] = useState("100");

  const load = useCallback(async () => {
    if (!companyId || !canRead) return;
    setLoading(true);
    setError("");
    try {
      const [j, e] = await Promise.all([
        apiGet<ScheduledJob[]>("/jobs", { company_id: companyId }),
        apiGet<JobExecution[]>("/jobs/executions", { company_id: companyId }),
      ]);
      setJobs(j);
      setExecutions(e);
    } catch (err) {
      setError(err instanceof Error ? err.message : "読み込みに失敗しました");
    } finally {
      setLoading(false);
    }
  }, [companyId, canRead]);

  useEffect(() => {
    load();
  }, [load]);

  const needsRunDay = frequency !== "daily";

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyId || !jobType) {
      setError("ジョブ種別は必須です。");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiPost<ScheduledJob>("/jobs", {
        company_id: companyId,
        job_type: jobType,
        frequency,
        run_hour: Number(runHour),
        run_day: needsRunDay ? Number(runDay) : null,
        priority: Number(priority),
      });
      setNotice("スケジュールジョブを登録しました。");
      setJobType("");
      setShowCreate(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const handleRun = async (job: ScheduledJob) => {
    setError("");
    setBusy(true);
    try {
      await apiPost<JobExecution>(`/jobs/${job.scheduled_job_id}/run`, {});
      setNotice(`「${job.job_type}」の実行をキューに登録しました。`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "実行に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const handleDispatch = async () => {
    if (!companyId) return;
    setError("");
    setBusy(true);
    try {
      const created = await apiPost<JobExecution[]>(`/jobs/dispatch?company_id=${encodeURIComponent(companyId)}`, {});
      setNotice(`実行時刻に達したジョブを ${created.length} 件ディスパッチしました。`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "ディスパッチに失敗しました");
    } finally {
      setBusy(false);
    }
  };

  if (!canRead) {
    return (
      <PageLayout title="スケジュールジョブ">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（master:read が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="スケジュールジョブ">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <CalendarClock className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">定期実行ジョブを登録・管理します。実行時刻に達したジョブはバックグラウンドワーカーが自動でディスパッチします（手動ディスパッチも可能）。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {canManage && (
          <div className="flex flex-wrap gap-2">
            {!showCreate && (
              <button type="button" onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
                <Plus className="h-4 w-4" aria-hidden="true" /> ジョブを登録
              </button>
            )}
            <button type="button" onClick={handleDispatch} disabled={busy} className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm disabled:opacity-50">
              <Zap className="h-4 w-4" aria-hidden="true" /> 期限到来ジョブを今すぐディスパッチ
            </button>
          </div>
        )}

        {showCreate && canManage && (
          <form onSubmit={handleCreate} aria-labelledby="job-create-heading" className="rounded-lg border p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 id="job-create-heading" className="text-sm font-semibold">スケジュールジョブの登録</h2>
              <button type="button" onClick={() => setShowCreate(false)} aria-label="フォームを閉じる" className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              <div>
                <label htmlFor="j-type" className="mb-1 block text-xs font-medium">ジョブ種別 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="j-type" type="text" required value={jobType} onChange={(e) => setJobType(e.target.value)} placeholder="例: monthly_close" className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="j-freq" className="mb-1 block text-xs font-medium">頻度</label>
                <select id="j-freq" value={frequency} onChange={(e) => setFrequency(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                  {FREQUENCIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="j-hour" className="mb-1 block text-xs font-medium">実行時（0-23）</label>
                <input id="j-hour" type="number" min={0} max={23} value={runHour} onChange={(e) => setRunHour(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              {needsRunDay && (
                <div>
                  <label htmlFor="j-day" className="mb-1 block text-xs font-medium">{frequency === "weekly" ? "曜日（0=月〜6=日）" : "日（1-31）"}</label>
                  <input id="j-day" type="number" min={frequency === "weekly" ? 0 : 1} max={frequency === "weekly" ? 6 : 31} value={runDay} onChange={(e) => setRunDay(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
              )}
              <div>
                <label htmlFor="j-prio" className="mb-1 block text-xs font-medium">優先度（小さいほど先）</label>
                <input id="j-prio" type="number" value={priority} onChange={(e) => setPriority(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
            </div>
            <button type="submit" disabled={busy} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} 登録
            </button>
          </form>
        )}

        {/* スケジュールジョブ一覧 */}
        {loading ? (
          <SkeletonTable rows={4} columns={5} />
        ) : (
          <section aria-labelledby="jobs-heading">
            <h2 id="jobs-heading" className="mb-2 text-sm font-semibold">登録済みジョブ</h2>
            {jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">スケジュールジョブがありません。</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <caption className="sr-only">スケジュールジョブ一覧</caption>
                  <thead className="bg-muted/50">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-medium">ジョブ種別</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">頻度</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">優先度</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">次回実行</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">状態</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.scheduled_job_id} className="border-t">
                        <td className="px-3 py-2">{j.job_type}</td>
                        <td className="px-3 py-2">{FREQUENCIES.find((f) => f.value === j.frequency)?.label ?? j.frequency}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{j.priority}</td>
                        <td className="px-3 py-2">{fmtDateTime(j.next_run_at)}</td>
                        <td className="px-3 py-2">{j.is_active ? "有効" : "無効"}</td>
                        <td className="px-3 py-2 text-right">
                          {canManage && (
                            <button type="button" onClick={() => handleRun(j)} disabled={busy} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50" aria-label={`${j.job_type} を今すぐ実行`}>
                              <Play className="h-3 w-3" aria-hidden="true" /> 実行
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* 実行履歴 */}
        {!loading && (
          <section aria-labelledby="exec-heading">
            <h2 id="exec-heading" className="mb-2 text-sm font-semibold">実行履歴</h2>
            {executions.length === 0 ? (
              <p className="text-sm text-muted-foreground">実行履歴がありません。</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <caption className="sr-only">ジョブ実行履歴</caption>
                  <thead className="bg-muted/50">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-medium">ジョブ種別</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">状態</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">試行</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">開始</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">終了</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">エラー</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.map((x) => (
                      <tr key={x.job_execution_id} className={`border-t ${x.status === "dead" ? "bg-destructive/5" : ""}`}>
                        <td className="px-3 py-2">{x.job_type}</td>
                        <td className="px-3 py-2">{STATUS_LABELS[x.status] ?? x.status}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{x.attempt_count}</td>
                        <td className="px-3 py-2">{fmtDateTime(x.started_at)}</td>
                        <td className="px-3 py-2">{fmtDateTime(x.finished_at)}</td>
                        <td className="px-3 py-2 text-destructive">{x.error_message || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>
    </PageLayout>
  );
}
