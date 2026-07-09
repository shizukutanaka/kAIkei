"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiPatch } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { ListChecks, CalendarPlus, Loader2, CheckCircle2 } from "lucide-react";

interface OfficeTask {
  office_task_id: string;
  title: string;
  task_type: string;
  due_date: string | null;
  status: string;
  period: string | null;
  completed_at: string | null;
}

interface Progress {
  total: number;
  todo: number;
  in_progress: number;
  done: number;
  completion_rate: number;
}

const STATUS_LABELS: Record<string, string> = { todo: "未着手", in_progress: "進行中", done: "完了" };
const STATUS_STYLES: Record<string, string> = {
  todo: "bg-gray-100 text-gray-600",
  in_progress: "bg-blue-100 text-blue-700",
  done: "bg-green-100 text-green-700",
};
const NEXT_STATUS: Record<string, string> = { todo: "in_progress", in_progress: "done", done: "todo" };

function currentMonth(): string {
  // 2026-07 形式。Dateは使わず固定の初期値はcompany切替後にユーザーが選ぶ。
  return "";
}

export default function OfficeTasksPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canManage = user?.permissions.includes("master:create") ?? false;

  const [period, setPeriod] = useState(currentMonth());
  const [tasks, setTasks] = useState<OfficeTask[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [generating, setGenerating] = useState(false);

  const fetchData = async () => {
    if (!companyId || !period) return;
    setLoading(true);
    setError("");
    try {
      const [taskData, progressData] = await Promise.all([
        apiGet<OfficeTask[]>("/office-tasks", { company_id: companyId, period, limit: "200" }),
        apiGet<Progress>("/office-tasks/progress", { company_id: companyId, period }),
      ]);
      setTasks(taskData);
      setProgress(progressData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && period) fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, period]);

  const handleGenerate = async () => {
    if (!companyId || !period) return;
    const [y, m] = period.split("-").map(Number);
    if (!y || !m) {
      setError("対象月を選択してください。");
      return;
    }
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      const created = await apiPost<OfficeTask[]>(
        `/office-tasks/generate?company_id=${encodeURIComponent(companyId)}`,
        { year: y, month: m }
      );
      setNotice(`${created.length}件の月次タスクを生成しました。`);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成に失敗しました");
    } finally {
      setGenerating(false);
    }
  };

  const handleAdvance = async (task: OfficeTask) => {
    if (!companyId) return;
    setError("");
    try {
      await apiPatch<OfficeTask>(
        `/office-tasks/${task.office_task_id}?company_id=${encodeURIComponent(companyId)}`,
        { status: NEXT_STATUS[task.status] ?? "todo" }
      );
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新に失敗しました");
    }
  };

  const pct = progress ? Math.round(progress.completion_rate * 100) : 0;

  return (
    <PageLayout title="月次業務タスク">
      <div className="space-y-6">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex items-center gap-2 text-muted-foreground">
            <ListChecks className="h-5 w-5" aria-hidden="true" />
            <p className="text-sm">月次決算などの定型業務をテンプレートから生成し、進捗を管理します。</p>
          </div>
          <div className="ml-auto flex items-end gap-2">
            <div>
              <label htmlFor="period" className="mb-1 block text-xs font-medium">対象月</label>
              <input
                id="period"
                type="month"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={!canManage || generating || !period}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
            >
              {generating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CalendarPlus className="h-4 w-4" aria-hidden="true" />}
              月次タスク生成
            </button>
          </div>
        </div>

        {error && <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {!period ? (
          <p className="text-sm text-muted-foreground">対象月を選択してください。</p>
        ) : (
          <>
            {progress && progress.total > 0 && (
              <div className="rounded-lg border p-4">
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-medium">進捗</span>
                  <span className="text-muted-foreground">
                    {progress.done}/{progress.total} 完了（{pct}%）
                  </span>
                </div>
                <div
                  className="h-2 w-full overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`月次業務進捗 ${pct}パーセント`}
                >
                  <div className="h-full rounded-full bg-green-600 transition-all" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )}

            {loading ? (
              <SkeletonTable rows={5} columns={4} />
            ) : tasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">タスクがありません。「月次タスク生成」で作成してください。</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <caption className="sr-only">{period} の月次業務タスク一覧</caption>
                  <thead className="bg-muted/50">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-medium">タスク</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">期日</th>
                      <th scope="col" className="px-3 py-2 text-center font-medium">状態</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((task) => (
                      <tr key={task.office_task_id} className="border-t">
                        <td className="px-3 py-2">{task.title}</td>
                        <td className="px-3 py-2">{task.due_date || "-"}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${STATUS_STYLES[task.status] ?? ""}`}>
                            {STATUS_LABELS[task.status] ?? task.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            onClick={() => handleAdvance(task)}
                            className="rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                            aria-label={`${task.title} の状態を ${STATUS_LABELS[NEXT_STATUS[task.status]] ?? ""} に変更`}
                          >
                            {task.status === "done" ? "未着手に戻す" : `${STATUS_LABELS[NEXT_STATUS[task.status]] ?? "進める"}へ`}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </PageLayout>
  );
}
