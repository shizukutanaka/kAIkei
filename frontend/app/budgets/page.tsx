"use client";

import { useState, useEffect, useCallback } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { formatYen } from "@/lib/format";
import { Wallet, Plus, Trash2, BarChart3, Loader2, CheckCircle2, X } from "lucide-react";

interface Account {
  account_id: string;
  account_code: string;
  account_name: string;
}

interface BudgetLineResponse {
  budget_line_id: string;
  account_id: string;
  month: number;
  budgeted_amount: string;
}

interface Budget {
  budget_id: string;
  company_id: string;
  fiscal_year: number;
  name: string;
  status: string;
  lines: BudgetLineResponse[];
}

interface VarianceLine {
  account_id: string;
  account_code: string;
  account_name: string;
  budgeted_amount: string;
  actual_amount: string;
  variance_amount: string;
  variance_rate: string;
  execution_rate: string;
  is_over_budget: boolean;
}

interface VarianceResponse {
  budget_id: string;
  fiscal_year: number;
  budgeted_total: string;
  actual_total: string;
  variance_total: string;
  execution_rate: string;
  over_budget_count: number;
  line_count: number;
  lines: VarianceLine[];
}

interface DraftLine {
  account_id: string;
  month: string;
  budgeted_amount: string;
}

function pct(value: string): string {
  const n = Number(value);
  return Number.isNaN(n) ? "-" : `${(n * 100).toFixed(1)}%`;
}

export default function BudgetsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("master:read") ?? false;
  const canCreate = user?.permissions.includes("master:create") ?? false;
  const canDelete = user?.permissions.includes("master:delete") ?? false;

  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // 作成フォーム
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [fiscalYear, setFiscalYear] = useState(String(new Date().getFullYear()));
  const [draftLines, setDraftLines] = useState<DraftLine[]>([{ account_id: "", month: "1", budgeted_amount: "" }]);
  const [saving, setSaving] = useState(false);

  // 予実分析
  const [variance, setVariance] = useState<VarianceResponse | null>(null);
  const [varianceLoading, setVarianceLoading] = useState(false);
  const [selectedBudgetId, setSelectedBudgetId] = useState<string | null>(null);

  const accountName = useCallback(
    (id: string) => {
      const a = accounts.find((x) => x.account_id === id);
      return a ? `${a.account_code} ${a.account_name}` : id.slice(0, 8);
    },
    [accounts]
  );

  const load = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const [b, a] = await Promise.all([
        apiGet<Budget[]>("/budgets", { company_id: companyId }),
        apiGet<Account[]>("/masters", { company_id: companyId }),
      ]);
      setBudgets(b);
      setAccounts(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "読み込みに失敗しました");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyId || !name || !fiscalYear) {
      setError("予算名と会計年度は必須です。");
      return;
    }
    const lines = draftLines
      .filter((l) => l.account_id && l.budgeted_amount)
      .map((l) => ({
        account_id: l.account_id,
        month: Number(l.month),
        budgeted_amount: l.budgeted_amount,
      }));
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await apiPost<Budget>("/budgets", {
        company_id: companyId,
        fiscal_year: Number(fiscalYear),
        name,
        lines,
      });
      setNotice("予算を作成しました。");
      setName("");
      setDraftLines([{ account_id: "", month: "1", budgeted_amount: "" }]);
      setShowCreate(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (budget: Budget) => {
    if (!companyId) return;
    setError("");
    try {
      await apiDelete(`/budgets/${budget.budget_id}`);
      setNotice(`予算「${budget.name}」を削除しました。`);
      if (selectedBudgetId === budget.budget_id) {
        setVariance(null);
        setSelectedBudgetId(null);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "削除に失敗しました");
    }
  };

  const handleVariance = async (budget: Budget) => {
    setVarianceLoading(true);
    setSelectedBudgetId(budget.budget_id);
    setError("");
    try {
      const data = await apiGet<VarianceResponse>(`/budgets/${budget.budget_id}/variance`);
      setVariance(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "予実分析の取得に失敗しました");
      setVariance(null);
    } finally {
      setVarianceLoading(false);
    }
  };

  const updateDraftLine = (idx: number, field: keyof DraftLine, value: string) => {
    setDraftLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  };

  if (!canRead) {
    return (
      <PageLayout title="予算管理">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（master:read が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="予算管理">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Wallet className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">会計年度単位で予算を編成し、勘定科目×月の予算額と実績（月次残高）の予実差異を分析します。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {canCreate && (
          <div>
            {!showCreate ? (
              <button type="button" onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
                <Plus className="h-4 w-4" aria-hidden="true" /> 予算を新規作成
              </button>
            ) : (
              <form onSubmit={handleCreate} aria-labelledby="create-heading" className="rounded-lg border p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h2 id="create-heading" className="text-sm font-semibold">予算の新規作成</h2>
                  <button type="button" onClick={() => setShowCreate(false)} aria-label="作成フォームを閉じる" className="text-muted-foreground hover:text-foreground">
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label htmlFor="b-name" className="mb-1 block text-xs font-medium">予算名 <span className="text-destructive" aria-hidden="true">*</span></label>
                    <input id="b-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
                  </div>
                  <div>
                    <label htmlFor="b-year" className="mb-1 block text-xs font-medium">会計年度 <span className="text-destructive" aria-hidden="true">*</span></label>
                    <input id="b-year" type="number" required min={2000} max={2999} value={fiscalYear} onChange={(e) => setFiscalYear(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
                  </div>
                </div>

                <fieldset className="mt-4">
                  <legend className="mb-2 text-xs font-medium">予算明細（勘定科目 × 月 × 予算額）</legend>
                  <div className="space-y-2">
                    {draftLines.map((line, idx) => (
                      <div key={idx} className="grid gap-2 md:grid-cols-[1fr_auto_auto_auto]">
                        <select aria-label={`明細${idx + 1}の勘定科目`} value={line.account_id} onChange={(e) => updateDraftLine(idx, "account_id", e.target.value)} className="rounded-md border px-3 py-2 text-sm">
                          <option value="">勘定科目を選択</option>
                          {accounts.map((a) => (
                            <option key={a.account_id} value={a.account_id}>{a.account_code} {a.account_name}</option>
                          ))}
                        </select>
                        <select aria-label={`明細${idx + 1}の月`} value={line.month} onChange={(e) => updateDraftLine(idx, "month", e.target.value)} className="rounded-md border px-2 py-2 text-sm">
                          {Array.from({ length: 12 }, (_, m) => (
                            <option key={m + 1} value={m + 1}>{m + 1}月</option>
                          ))}
                        </select>
                        <input aria-label={`明細${idx + 1}の予算額`} type="number" min={0} step="1" placeholder="予算額" value={line.budgeted_amount} onChange={(e) => updateDraftLine(idx, "budgeted_amount", e.target.value)} className="w-32 rounded-md border px-3 py-2 text-sm" />
                        <button type="button" onClick={() => setDraftLines((prev) => prev.filter((_, i) => i !== idx))} disabled={draftLines.length === 1} aria-label={`明細${idx + 1}を削除`} className="inline-flex items-center rounded-md border px-2 text-muted-foreground hover:text-destructive disabled:opacity-40">
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" onClick={() => setDraftLines((prev) => [...prev, { account_id: "", month: "1", budgeted_amount: "" }])} className="mt-2 inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs">
                    <Plus className="h-3 w-3" aria-hidden="true" /> 明細を追加
                  </button>
                </fieldset>

                <button type="submit" disabled={saving} className="mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} 作成
                </button>
              </form>
            )}
          </div>
        )}

        {/* 予算一覧 */}
        {loading ? (
          <SkeletonTable rows={4} columns={4} />
        ) : budgets.length === 0 ? (
          <p className="text-sm text-muted-foreground">予算がありません。{canCreate ? "「予算を新規作成」から編成してください。" : ""}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">予算一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">会計年度</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">予算名</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">明細数</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">状態</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {budgets.map((b) => (
                  <tr key={b.budget_id} className="border-t">
                    <td className="px-3 py-2 tabular-nums">{b.fiscal_year}</td>
                    <td className="px-3 py-2">{b.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{b.lines.length}</td>
                    <td className="px-3 py-2">{b.status}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="inline-flex gap-1">
                        <button type="button" onClick={() => handleVariance(b)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground" aria-label={`${b.name} の予実分析`}>
                          <BarChart3 className="h-3 w-3" aria-hidden="true" /> 予実
                        </button>
                        {canDelete && (
                          <button type="button" onClick={() => handleDelete(b)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-destructive" aria-label={`${b.name} を削除`}>
                            <Trash2 className="h-3 w-3" aria-hidden="true" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 予実分析 */}
        {selectedBudgetId && (
          <section aria-labelledby="variance-heading" className="rounded-lg border p-4">
            <h2 id="variance-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <BarChart3 className="h-4 w-4" aria-hidden="true" /> 予実分析
            </h2>
            {varianceLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> 読み込み中…</div>
            ) : variance ? (
              <div className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-4">
                  <div className="rounded-md border p-3"><p className="text-xs text-muted-foreground">予算合計</p><p className="tabular-nums">{formatYen(variance.budgeted_total)}</p></div>
                  <div className="rounded-md border p-3"><p className="text-xs text-muted-foreground">実績合計</p><p className="tabular-nums">{formatYen(variance.actual_total)}</p></div>
                  <div className="rounded-md border p-3"><p className="text-xs text-muted-foreground">差異</p><p className="tabular-nums">{formatYen(variance.variance_total)}</p></div>
                  <div className="rounded-md border p-3"><p className="text-xs text-muted-foreground">執行率 / 予算超過</p><p className="tabular-nums">{pct(variance.execution_rate)} / {variance.over_budget_count}件</p></div>
                </div>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="w-full text-sm">
                    <caption className="sr-only">勘定科目別の予実差異</caption>
                    <thead className="bg-muted/50">
                      <tr>
                        <th scope="col" className="px-3 py-2 text-left font-medium">勘定科目</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">予算</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">実績</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">差異</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">執行率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {variance.lines.map((l) => (
                        <tr key={l.account_id} className={`border-t ${l.is_over_budget ? "bg-destructive/5" : ""}`}>
                          <td className="px-3 py-2">{l.account_code} {l.account_name || accountName(l.account_id)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatYen(l.budgeted_amount)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatYen(l.actual_amount)}</td>
                          <td className={`px-3 py-2 text-right tabular-nums ${l.is_over_budget ? "text-destructive" : ""}`}>{formatYen(l.variance_amount)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{pct(l.execution_rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">予実データを取得できませんでした。</p>
            )}
          </section>
        )}
      </div>
    </PageLayout>
  );
}
