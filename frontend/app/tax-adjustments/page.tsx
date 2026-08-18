"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Scale, Plus, Trash2, Calculator, Loader2, CheckCircle2 } from "lucide-react";

interface AdjustmentRule {
  tax_adjustment_rule_id: string;
  name: string;
  adjustment_type: string;
  calculation_method: string;
  rate: string | null;
  limit_amount: string | null;
  fixed_amount: string | null;
  target_account_code: string | null;
  is_active: boolean;
}

interface ComputeResult {
  accounting_income: string;
  taxable_income: string;
  total_additions: string;
  total_subtractions: string;
  adjustments: { rule_id: string; name: string; adjustment_type: string; amount: string }[];
}

const TYPE_LABELS: Record<string, string> = { addition: "加算", subtraction: "減算" };
const METHOD_LABELS: Record<string, string> = {
  fixed: "固定額",
  rate: "料率",
  excess_over_limit: "限度超過額",
};

function yen(v: string | null): string {
  if (v === null) return "-";
  const n = Number(v);
  return Number.isNaN(n) ? v : `¥${n.toLocaleString("ja-JP")}`;
}

export default function TaxAdjustmentsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("master:read") ?? false;
  const canCreate = user?.permissions.includes("master:create") ?? false;
  const canDelete = user?.permissions.includes("master:delete") ?? false;

  const [rules, setRules] = useState<AdjustmentRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // 新規ルール
  const [name, setName] = useState("");
  const [adjType, setAdjType] = useState("addition");
  const [method, setMethod] = useState("fixed");
  const [rate, setRate] = useState("");
  const [limitAmount, setLimitAmount] = useState("");
  const [fixedAmount, setFixedAmount] = useState("");
  const [creating, setCreating] = useState(false);

  // 計算
  const [accountingIncome, setAccountingIncome] = useState("");
  const [baseAmounts, setBaseAmounts] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ComputeResult | null>(null);
  const [computing, setComputing] = useState(false);

  const fetchRules = async () => {
    if (!companyId || !canRead) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<AdjustmentRule[]>("/tax-adjustments/rules", { company_id: companyId });
      setRules(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && canRead) fetchRules();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, canRead]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyId || !name) return;
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const body: Record<string, unknown> = { name, adjustment_type: adjType, calculation_method: method };
      if (method === "rate" && rate) body.rate = rate;
      if (method === "excess_over_limit" && limitAmount) body.limit_amount = limitAmount;
      if (method === "fixed" && fixedAmount) body.fixed_amount = fixedAmount;
      await apiPost<AdjustmentRule>(`/tax-adjustments/rules?company_id=${encodeURIComponent(companyId)}`, body);
      setNotice("調整ルールを作成しました。");
      setName(""); setRate(""); setLimitAmount(""); setFixedAmount("");
      await fetchRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!companyId) return;
    setError("");
    try {
      await apiDelete(`/tax-adjustments/rules/${id}?company_id=${encodeURIComponent(companyId)}`);
      await fetchRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "削除に失敗しました");
    }
  };

  const handleCompute = async () => {
    if (!companyId || !accountingIncome) return;
    setComputing(true);
    setError("");
    try {
      const base: Record<string, number> = {};
      for (const [k, v] of Object.entries(baseAmounts)) {
        if (v) base[k] = Number(v);
      }
      const data = await apiPost<ComputeResult>(
        `/tax-adjustments/compute?company_id=${encodeURIComponent(companyId)}`,
        { accounting_income: accountingIncome, base_amounts: base }
      );
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "計算に失敗しました");
    } finally {
      setComputing(false);
    }
  };

  const rulesNeedingBase = rules.filter(
    (r) => r.is_active && (r.calculation_method === "rate" || r.calculation_method === "excess_over_limit")
  );

  if (!canRead) {
    return (
      <PageLayout title="税務調整">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="税務調整">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Scale className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">加算・減算の税務調整ルールを設定し、会計上利益から課税所得を計算します（別表四）。</p>
        </div>

        {error && <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {/* 新規ルール */}
        {canCreate && (
          <form onSubmit={handleCreate} aria-labelledby="rule-heading" className="rounded-lg border p-4">
            <h2 id="rule-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold"><Plus className="h-4 w-4" aria-hidden="true" /> 調整ルールの追加</h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              <div>
                <label htmlFor="r-name" className="mb-1 block text-xs font-medium">名称 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="r-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="例: 交際費限度超過" className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="r-type" className="mb-1 block text-xs font-medium">区分</label>
                <select id="r-type" value={adjType} onChange={(e) => setAdjType(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                  <option value="addition">加算</option>
                  <option value="subtraction">減算</option>
                </select>
              </div>
              <div>
                <label htmlFor="r-method" className="mb-1 block text-xs font-medium">計算方法</label>
                <select id="r-method" value={method} onChange={(e) => setMethod(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                  <option value="fixed">固定額</option>
                  <option value="rate">料率</option>
                  <option value="excess_over_limit">限度超過額</option>
                </select>
              </div>
              {method === "fixed" && (
                <div>
                  <label htmlFor="r-fixed" className="mb-1 block text-xs font-medium">固定額</label>
                  <input id="r-fixed" type="number" value={fixedAmount} onChange={(e) => setFixedAmount(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
              )}
              {method === "rate" && (
                <div>
                  <label htmlFor="r-rate" className="mb-1 block text-xs font-medium">料率（例: 0.1）</label>
                  <input id="r-rate" type="number" step="0.0001" value={rate} onChange={(e) => setRate(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
              )}
              {method === "excess_over_limit" && (
                <div>
                  <label htmlFor="r-limit" className="mb-1 block text-xs font-medium">限度額</label>
                  <input id="r-limit" type="number" value={limitAmount} onChange={(e) => setLimitAmount(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
              )}
            </div>
            <button type="submit" disabled={creating || !name} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {creating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} 追加
            </button>
          </form>
        )}

        {/* ルール一覧 */}
        {loading ? (
          <SkeletonTable rows={4} columns={4} />
        ) : rules.length === 0 ? (
          <p className="text-sm text-muted-foreground">調整ルールがありません。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">税務調整ルールの一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">名称</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">区分</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">計算方法</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">パラメータ</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.tax_adjustment_rule_id} className="border-t">
                    <td className="px-3 py-2">{r.name}</td>
                    <td className="px-3 py-2 text-center">{TYPE_LABELS[r.adjustment_type] ?? r.adjustment_type}</td>
                    <td className="px-3 py-2">{METHOD_LABELS[r.calculation_method] ?? r.calculation_method}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.calculation_method === "fixed" && yen(r.fixed_amount)}
                      {r.calculation_method === "rate" && (r.rate ?? "-")}
                      {r.calculation_method === "excess_over_limit" && yen(r.limit_amount)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {canDelete && (
                        <button type="button" onClick={() => handleDelete(r.tax_adjustment_rule_id)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground" aria-label={`ルール ${r.name} を削除`}>
                          <Trash2 className="h-3 w-3" aria-hidden="true" /> 削除
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 課税所得計算 */}
        <section aria-labelledby="compute-heading" className="rounded-lg border p-4">
          <h2 id="compute-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold"><Calculator className="h-4 w-4" aria-hidden="true" /> 課税所得の計算</h2>
          <div className="space-y-3">
            <div>
              <label htmlFor="acc-income" className="mb-1 block text-xs font-medium">会計上の当期純利益 <span className="text-destructive" aria-hidden="true">*</span></label>
              <input id="acc-income" type="number" value={accountingIncome} onChange={(e) => setAccountingIncome(e.target.value)} className="w-full max-w-xs rounded-md border px-3 py-2 text-sm" />
            </div>
            {rulesNeedingBase.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">計算基礎額（料率・限度超過ルール）</p>
                {rulesNeedingBase.map((r) => (
                  <div key={r.tax_adjustment_rule_id} className="flex items-center gap-2">
                    <label htmlFor={`base-${r.tax_adjustment_rule_id}`} className="w-56 text-xs">{r.name}</label>
                    <input
                      id={`base-${r.tax_adjustment_rule_id}`}
                      type="number"
                      value={baseAmounts[r.tax_adjustment_rule_id] ?? ""}
                      onChange={(e) => setBaseAmounts({ ...baseAmounts, [r.tax_adjustment_rule_id]: e.target.value })}
                      className="w-40 rounded-md border px-3 py-1.5 text-sm"
                    />
                  </div>
                ))}
              </div>
            )}
            <button type="button" onClick={handleCompute} disabled={computing || !accountingIncome} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {computing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Calculator className="h-4 w-4" aria-hidden="true" />} 計算
            </button>
          </div>

          {result && (
            <div className="mt-4 rounded-md border bg-muted/30 p-4 text-sm">
              <dl className="grid gap-1 sm:grid-cols-2">
                <dt className="text-muted-foreground">会計上利益</dt><dd className="text-right tabular-nums">{yen(result.accounting_income)}</dd>
                <dt className="text-muted-foreground">加算合計</dt><dd className="text-right tabular-nums text-red-700">+{yen(result.total_additions)}</dd>
                <dt className="text-muted-foreground">減算合計</dt><dd className="text-right tabular-nums text-blue-700">-{yen(result.total_subtractions)}</dd>
                <dt className="font-semibold">課税所得</dt><dd className="text-right font-semibold tabular-nums">{yen(result.taxable_income)}</dd>
              </dl>
            </div>
          )}
        </section>
      </div>
    </PageLayout>
  );
}
