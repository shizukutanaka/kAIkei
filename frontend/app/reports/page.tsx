"use client";

import { useState } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useToast } from "@/components/toast";
import { FileText, Search, Users, Gift } from "lucide-react";
import { SkeletonTable } from "@/components/skeleton";

interface TrialBalanceAccount {
  account_code: string;
  account_name: string;
  account_type: string;
  debit_total: string;
  credit_total: string;
  balance: string;
  display_debit: string;
  display_credit: string;
}

interface TrialBalance {
  as_of: string;
  accounts: TrialBalanceAccount[];
  total_debit: string;
  total_credit: string;
  is_balanced: boolean;
}

interface PayrollSummaryItem {
  payroll_id: string;
  employee_id: string;
  payroll_year: number;
  payroll_month: number;
  base_salary: string;
  overtime_hours: string;
  overtime_pay: string;
  total_gross: string;
  income_tax: string;
  social_insurance: string;
  total_deductions: string;
  net_pay: string;
  status: string;
  employee_name: string | null;
}

interface BonusSummaryItem {
  bonus_id: string;
  employee_id: string;
  bonus_year: number;
  bonus_term: string;
  bonus_amount: string;
  bonus_base_months: string;
  performance_factor: string;
  income_tax: string;
  social_insurance: string;
  total_deductions: string;
  net_pay: string;
  status: string;
  employee_name: string | null;
}

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  asset: "資産",
  liability: "負債",
  equity: "純資産",
  revenue: "収益",
  expense: "費用",
};

export default function ReportsPage() {
  const { companyId } = useCompany();
  const { toast } = useToast();
  const [asOf, setAsOf] = useState(new Date().toISOString().split("T")[0]);
  const [reportType, setReportType] = useState<"trial-balance" | "monthly" | "payroll" | "bonus">("trial-balance");
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [month, setMonth] = useState((new Date().getMonth() + 1).toString());
  const [data, setData] = useState<TrialBalance | null>(null);
  const [monthlyData, setMonthlyData] = useState<Record<string, unknown> | null>(null);
  const [payrollData, setPayrollData] = useState<PayrollSummaryItem[] | null>(null);
  const [bonusData, setBonusData] = useState<BonusSummaryItem[] | null>(null);
  const [bonusTerm, setBonusTerm] = useState("summer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleFetch = async () => {
    if (!companyId) {
      setError("サイドバーで会社IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    setMonthlyData(null);
    setPayrollData(null);
    setBonusData(null);

    try {
      if (reportType === "trial-balance") {
        const result = await apiGet<TrialBalance>("/reports/trial-balance", {
          company_id: companyId,
          as_of: asOf,
        });
        setData(result);
        toast("試算表を取得しました", "success");
      } else if (reportType === "monthly") {
        const result = await apiGet<Record<string, unknown>>("/reports/monthly-balances", {
          company_id: companyId,
          year,
          month,
        });
        setMonthlyData(result);
        toast("月次残高を取得しました", "success");
      } else if (reportType === "payroll") {
        const result = await apiGet<PayrollSummaryItem[]>("/payroll/records", {
          company_id: companyId,
          payroll_year: year,
          payroll_month: month,
        });
        setPayrollData(result);
        toast("給与サマリーを取得しました", "success");
      } else {
        const result = await apiGet<BonusSummaryItem[]>("/bonus/records", {
          company_id: companyId,
          bonus_year: year,
          bonus_term: bonusTerm,
        });
        setBonusData(result);
        toast("賞与サマリーを取得しました", "success");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
      toast("レポートの取得に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
        <div className="mb-6 flex items-center gap-3">
          <FileText className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">帳票</h1>
        </div>

        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex gap-2">
            <button
              onClick={() => setReportType("trial-balance")}
              className={`rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "trial-balance" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              試算表
            </button>
            <button
              onClick={() => setReportType("monthly")}
              className={`rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "monthly" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              月次残高
            </button>
            <button
              onClick={() => setReportType("payroll")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "payroll" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <Users className="h-4 w-4" />
              給与サマリー
            </button>
            <button
              onClick={() => setReportType("bonus")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "bonus" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <Gift className="h-4 w-4" />
              賞与サマリー
            </button>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">会社ID</label>
              <div className="w-full rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                {companyId || "未設定"}
              </div>
            </div>
            {reportType === "trial-balance" ? (
              <div>
                <label className="mb-1 block text-sm font-medium">基準日</label>
                <input
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
              </div>
            ) : (
              <>
                <div>
                  <label className="mb-1 block text-sm font-medium">年</label>
                  <input
                    type="number"
                    value={year}
                    onChange={(e) => setYear(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">月</label>
                  <select
                    value={month}
                    onChange={(e) => setMonth(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm"
                  >
                    {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                      <option key={m} value={m}>{m}月</option>
                    ))}
                  </select>
                </div>
              </>
            )}
            {reportType === "payroll" && (
              <div className="flex items-end">
                <p className="text-xs text-muted-foreground">給与計算実行後にデータが表示されます</p>
              </div>
            )}
            {reportType === "bonus" && (
              <div>
                <label className="mb-1 block text-sm font-medium">賞与区分</label>
                <select
                  value={bonusTerm}
                  onChange={(e) => setBonusTerm(e.target.value)}
                  className="w-full rounded-md border px-3 py-2 text-sm"
                >
                  <option value="summer">夏季賞与</option>
                  <option value="winter">冬季賞与</option>
                  <option value="yearend">年末賞与</option>
                  <option value="other">その他</option>
                </select>
              </div>
            )}
          </div>

          <button
            onClick={handleFetch}
            disabled={loading || !companyId}
            className="mt-4 flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
            {loading ? "取得中..." : "帳票取得"}
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {data && (
          <div className="overflow-hidden rounded-lg border">
            <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">試算表 — {data.as_of}</h2>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${data.is_balanced ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                {data.is_balanced ? "貸借一致" : "貸借不一致"}
              </span>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">科目コード</th>
                  <th className="px-4 py-2 text-left font-medium">科目名</th>
                  <th className="px-4 py-2 text-left font-medium">区分</th>
                  <th className="px-4 py-2 text-right font-medium">借方</th>
                  <th className="px-4 py-2 text-right font-medium">貸方</th>
                </tr>
              </thead>
              <tbody>
                {data.accounts.map((a) => (
                  <tr key={a.account_code} className="border-t">
                    <td className="px-4 py-2 font-mono">{a.account_code}</td>
                    <td className="px-4 py-2">{a.account_name}</td>
                    <td className="px-4 py-2">{ACCOUNT_TYPE_LABELS[a.account_type] || a.account_type}</td>
                    <td className="px-4 py-2 text-right">{a.display_debit !== "0" ? a.display_debit : ""}</td>
                    <td className="px-4 py-2 text-right">{a.display_credit !== "0" ? a.display_credit : ""}</td>
                  </tr>
                ))}
                <tr className="border-t-2 bg-muted/30 font-bold">
                  <td className="px-4 py-3" colSpan={3}>合計</td>
                  <td className="px-4 py-3 text-right">{data.total_debit}</td>
                  <td className="px-4 py-3 text-right">{data.total_credit}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {loading && reportType === "payroll" && (
          <SkeletonTable rows={5} columns={6} />
        )}

        {payrollData && payrollData.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
            <div className="border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">給与サマリー — {year}年{month}月</h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">従業員</th>
                  <th className="px-4 py-2 text-right font-medium">基本給</th>
                  <th className="px-4 py-2 text-right font-medium">残業代</th>
                  <th className="px-4 py-2 text-right font-medium">総支給額</th>
                  <th className="px-4 py-2 text-right font-medium">控除額</th>
                  <th className="px-4 py-2 text-right font-medium">差引支給額</th>
                </tr>
              </thead>
              <tbody>
                {payrollData.map((r) => (
                  <tr key={r.payroll_id} className="border-t">
                    <td className="px-4 py-2">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.base_salary).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.overtime_pay).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-medium">¥{parseInt(r.total_gross).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right text-red-600">¥{parseInt(r.total_deductions).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-bold">¥{parseInt(r.net_pay).toLocaleString()}</td>
                  </tr>
                ))}
                {(() => {
                  const totalGross = payrollData.reduce((s, r) => s + parseInt(r.total_gross), 0);
                  const totalDed = payrollData.reduce((s, r) => s + parseInt(r.total_deductions), 0);
                  const totalNet = payrollData.reduce((s, r) => s + parseInt(r.net_pay), 0);
                  return (
                    <tr className="border-t-2 bg-muted/30 font-bold">
                      <td className="px-4 py-3">合計</td>
                      <td colSpan={2} />
                      <td className="px-4 py-3 text-right">¥{totalGross.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-red-600">¥{totalDed.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right">¥{totalNet.toLocaleString()}</td>
                    </tr>
                  );
                })()}
              </tbody>
            </table>
          </div>
        )}

        {payrollData && payrollData.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
            <Users className="mb-3 h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">該当月の給与データがありません。給与計算を実行してください。</p>
          </div>
        )}

        {loading && reportType === "bonus" && (
          <SkeletonTable rows={5} columns={6} />
        )}

        {bonusData && bonusData.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
            <div className="border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">
                賞与サマリー — {year}年 ({bonusTerm === "summer" ? "夏季" : bonusTerm === "winter" ? "冬季" : bonusTerm === "yearend" ? "年末" : "その他"})
              </h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">従業員</th>
                  <th className="px-4 py-2 text-right font-medium">基準月数</th>
                  <th className="px-4 py-2 text-right font-medium">業績係数</th>
                  <th className="px-4 py-2 text-right font-medium">賞与額</th>
                  <th className="px-4 py-2 text-right font-medium">控除額</th>
                  <th className="px-4 py-2 text-right font-medium">差引支給額</th>
                </tr>
              </thead>
              <tbody>
                {bonusData.map((r) => (
                  <tr key={r.bonus_id} className="border-t">
                    <td className="px-4 py-2">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                    <td className="px-4 py-2 text-right">{parseFloat(r.bonus_base_months).toFixed(1)}ヶ月</td>
                    <td className="px-4 py-2 text-right">{parseFloat(r.performance_factor).toFixed(2)}</td>
                    <td className="px-4 py-2 text-right font-medium">¥{parseInt(r.bonus_amount).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right text-red-600">¥{parseInt(r.total_deductions).toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-bold">¥{parseInt(r.net_pay).toLocaleString()}</td>
                  </tr>
                ))}
                {(() => {
                  const totalGross = bonusData.reduce((s, r) => s + parseInt(r.bonus_amount), 0);
                  const totalDed = bonusData.reduce((s, r) => s + parseInt(r.total_deductions), 0);
                  const totalNet = bonusData.reduce((s, r) => s + parseInt(r.net_pay), 0);
                  return (
                    <tr className="border-t-2 bg-muted/30 font-bold">
                      <td className="px-4 py-3">合計</td>
                      <td colSpan={2} />
                      <td className="px-4 py-3 text-right">¥{totalGross.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-red-600">¥{totalDed.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right">¥{totalNet.toLocaleString()}</td>
                    </tr>
                  );
                })()}
              </tbody>
            </table>
          </div>
        )}

        {bonusData && bonusData.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
            <Gift className="mb-3 h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">該当の賞与データがありません。賞与計算を実行してください。</p>
          </div>
        )}

        {monthlyData && (
          <div className="overflow-hidden rounded-lg border">
            <div className="border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">
                月次残高 — {monthlyData.year as string}年{monthlyData.month as string}月
              </h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">科目コード</th>
                  <th className="px-4 py-2 text-left font-medium">科目名</th>
                  <th className="px-4 py-2 text-right font-medium">借方</th>
                  <th className="px-4 py-2 text-right font-medium">貸方</th>
                  <th className="px-4 py-2 text-right font-medium">残高</th>
                </tr>
              </thead>
              <tbody>
                {(monthlyData.items as Array<Record<string, string>>)?.map((item, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-4 py-2 font-mono">{item.account_code}</td>
                    <td className="px-4 py-2">{item.account_name}</td>
                    <td className="px-4 py-2 text-right">{item.debit_total}</td>
                    <td className="px-4 py-2 text-right">{item.credit_total}</td>
                    <td className="px-4 py-2 text-right">{item.balance}</td>
                  </tr>
                ))}
                <tr className="border-t-2 bg-muted/30 font-bold">
                  <td className="px-4 py-3" colSpan={2}>合計</td>
                  <td className="px-4 py-3 text-right">{monthlyData.total_debit as string}</td>
                  <td className="px-4 py-3 text-right">{monthlyData.total_credit as string}</td>
                  <td className="px-4 py-3 text-right">
                    {monthlyData.is_balanced ? "一致" : "不一致"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
    </PageLayout>
  );
}
