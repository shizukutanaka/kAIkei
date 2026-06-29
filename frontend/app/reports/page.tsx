"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { FileText, Search, Users, Gift, Clock, Wallet, TrendingUp, Scale, Download, Lock, LockOpen, RefreshCw, Loader2 } from "lucide-react";
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

interface IncomeStatement {
  as_of: string;
  revenues: Array<{ account_code: string; account_name: string; amount: string }>;
  total_revenue: string;
  expenses: Array<{ account_code: string; account_name: string; amount: string }>;
  total_expense: string;
  net_income: string;
}

interface BalanceSheet {
  as_of: string;
  assets: Array<{ account_code: string; account_name: string; amount: string }>;
  total_assets: string;
  liabilities: Array<{ account_code: string; account_name: string; amount: string }>;
  total_liabilities: string;
  equity: Array<{ account_code: string; account_name: string; amount: string }>;
  total_equity: string;
  is_balanced: boolean;
}

interface CashFlowStatement {
  as_of: string;
  operating: { items: Array<{ item: string; amount: string }>; subtotal: string };
  investing: { items: Array<{ item: string; amount: string }>; subtotal: string };
  financing: { items: Array<{ item: string; amount: string }>; subtotal: string };
  net_cash_flow: string;
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
  const { confirm } = useConfirm();
  const [asOf, setAsOf] = useState(new Date().toISOString().split("T")[0]);
  const [reportType, setReportType] = useState<"trial-balance" | "monthly" | "payroll" | "bonus" | "attendance" | "expenses" | "income-statement" | "balance-sheet" | "cash-flow">("trial-balance");
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [month, setMonth] = useState((new Date().getMonth() + 1).toString());
  const [data, setData] = useState<TrialBalance | null>(null);
  const [monthlyData, setMonthlyData] = useState<Record<string, unknown> | null>(null);
  const [payrollData, setPayrollData] = useState<PayrollSummaryItem[] | null>(null);
  const [bonusData, setBonusData] = useState<BonusSummaryItem[] | null>(null);
  const [attendanceData, setAttendanceData] = useState<Array<{ employee_id: string; employee_name: string; employee_code: string; days: number; total_work_minutes: number; total_overtime_minutes: number; paid_leave_days: number; absent_days: number }> | null>(null);
  const [expenseData, setExpenseData] = useState<Array<{ report_id: string; title: string; employee_name: string | null; total_amount: string; status: string; report_date: string }> | null>(null);
  const [incomeData, setIncomeData] = useState<IncomeStatement | null>(null);
  const [balanceData, setBalanceData] = useState<BalanceSheet | null>(null);
  const [cashFlowData, setCashFlowData] = useState<CashFlowStatement | null>(null);
  const [bonusTerm, setBonusTerm] = useState("summer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [periodCloses, setPeriodCloses] = useState<Array<{ close_id: string; year: number; month: number; status: string; closed_at: string | null }>>([]);
  const [closeLoading, setCloseLoading] = useState<string | null>(null);
  const [exportLoading, setExportLoading] = useState(false);

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
    setAttendanceData(null);
    setExpenseData(null);
    setIncomeData(null);
    setBalanceData(null);
    setCashFlowData(null);

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
        const result = await apiGet<{ items: PayrollSummaryItem[]; total: number }>("/payroll/records", {
          company_id: companyId,
          payroll_year: year,
          payroll_month: month,
        });
        setPayrollData(result.items);
        toast("給与サマリーを取得しました", "success");
      } else if (reportType === "attendance") {
        const result = await apiGet<Array<{ employee_id: string; employee_name: string; employee_code: string; days: number; total_work_minutes: number; total_overtime_minutes: number; paid_leave_days: number; absent_days: number }>>("/attendance/summary", {
          company_id: companyId,
          year,
          month,
        });
        setAttendanceData(result);
        toast("勤怠集計を取得しました", "success");
      } else if (reportType === "expenses") {
        const result = await apiGet<{ items: Array<{ report_id: string; title: string; employee_name: string | null; total_amount: string; status: string; report_date: string }>; total: number }>("/expenses/reports", {
          company_id: companyId,
        });
        setExpenseData(result.items);
        toast("経費集計を取得しました", "success");
      } else if (reportType === "income-statement") {
        const result = await apiGet<IncomeStatement>("/reports/income-statement", {
          company_id: companyId,
          as_of: asOf,
        });
        setIncomeData(result);
        toast("損益計算書を取得しました", "success");
      } else if (reportType === "balance-sheet") {
        const result = await apiGet<BalanceSheet>("/reports/balance-sheet", {
          company_id: companyId,
          as_of: asOf,
        });
        setBalanceData(result);
        toast("貸借対照表を取得しました", "success");
      } else if (reportType === "cash-flow") {
        const result = await apiGet<CashFlowStatement>("/reports/cash-flow", {
          company_id: companyId,
          as_of: asOf,
        });
        setCashFlowData(result);
        toast("キャッシュフロー計算書を取得しました", "success");
      } else {
        const result = await apiGet<{ items: BonusSummaryItem[]; total: number; page: number; page_size: number }>("/bonus/records", {
          company_id: companyId,
          bonus_year: year,
          bonus_term: bonusTerm,
        });
        setBonusData(result.items);
        toast("賞与サマリーを取得しました", "success");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
      toast("レポートの取得に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = async () => {
    if (!companyId) return;
    setExportLoading(true);
    const exportPath = reportType === "trial-balance" ? "/reports/trial-balance/export"
      : reportType === "income-statement" ? "/reports/income-statement/export"
      : reportType === "balance-sheet" ? "/reports/balance-sheet/export"
      : "/reports/cash-flow/export";
    try {
      const csv = await apiGet<string>(exportPath, {
        company_id: companyId,
        as_of: asOf,
      });
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${reportType}_${asOf}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSVを出力しました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "CSV出力に失敗しました", "error");
    } finally {
      setExportLoading(false);
    }
  };

  const fetchPeriodCloses = async () => {
    if (!companyId) return;
    try {
      const result = await apiGet<Array<{ close_id: string; year: number; month: number; status: string; closed_at: string | null }>>("/reports/period-closes", {
        company_id: companyId,
        year: new Date().getFullYear().toString(),
      });
      setPeriodCloses(result);
    } catch {
      // API not running
    }
  };

  const handlePeriodClose = async (month: number, action: "close" | "reopen") => {
    if (!companyId) return;
    const ok = await confirm({
      title: action === "close" ? "月次締切" : "月次締切再開",
      message: `${month}月を${action === "close" ? "締切" : "再開"}しますか？`,
      confirmText: action === "close" ? "締切" : "再開",
      variant: "default",
    });
    if (!ok) return;
    setCloseLoading(`${month}-${action}`);
    try {
      await apiPost("/reports/period-closes", null, {
        company_id: companyId,
        year: new Date().getFullYear().toString(),
        month: month.toString(),
        action,
      });
      toast(`${month}月を${action === "close" ? "締切" : "再開"}しました`, "success");
      await fetchPeriodCloses();
    } catch (err) {
      toast(err instanceof Error ? err.message : "操作に失敗しました", "error");
    } finally {
      setCloseLoading(null);
    }
  };

  useEffect(() => {
    if (companyId) fetchPeriodCloses();
  }, [companyId]);

  return (
    <PageLayout>
        <div className="mb-6 flex items-center gap-3">
          <FileText className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">帳票</h1>
        </div>

        {!companyId && (
          <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
            サイドバーで会社を選択してください。
          </div>
        )}

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
            <button
              onClick={() => setReportType("attendance")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "attendance" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <Clock className="h-4 w-4" />
              勤怠集計
            </button>
            <button
              onClick={() => setReportType("expenses")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "expenses" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <Wallet className="h-4 w-4" />
              経費集計
            </button>
            <button
              onClick={() => setReportType("income-statement")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "income-statement" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <TrendingUp className="h-4 w-4" />
              損益計算書
            </button>
            <button
              onClick={() => setReportType("balance-sheet")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "balance-sheet" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <Scale className="h-4 w-4" />
              貸借対照表
            </button>
            <button
              onClick={() => setReportType("cash-flow")}
              className={`flex items-center gap-1 rounded-md px-4 py-2 text-sm font-medium ${
                reportType === "cash-flow" ? "bg-primary text-primary-foreground" : "border"
              }`}
            >
              <Wallet className="h-4 w-4" />
              キャッシュフロー
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {reportType === "trial-balance" || reportType === "income-statement" || reportType === "balance-sheet" || reportType === "cash-flow" ? (
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
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "取得中..." : "帳票取得"}
          </button>

          {(reportType === "trial-balance" || reportType === "income-statement" || reportType === "balance-sheet" || reportType === "cash-flow") && (
            <button
              onClick={() => handleExportCSV()}
              disabled={!companyId || exportLoading}
              className="mt-4 ml-2 flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              {exportLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {exportLoading ? "出力中..." : "CSV出力"}
            </button>
          )}
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {data && (
          <div className="overflow-x-auto rounded-lg border">
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
          <div className="overflow-x-auto rounded-lg border">
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
          <div className="overflow-x-auto rounded-lg border">
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
          <div className="overflow-x-auto rounded-lg border">
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

        {attendanceData && attendanceData.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <div className="border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">勤怠集計 — {year}年{month}月</h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">従業員コード</th>
                  <th className="px-4 py-3 text-left font-medium">氏名</th>
                  <th className="px-4 py-3 text-right font-medium">出勤日数</th>
                  <th className="px-4 py-3 text-right font-medium">総勤務時間</th>
                  <th className="px-4 py-3 text-right font-medium">総残業時間</th>
                  <th className="px-4 py-3 text-right font-medium">有給日数</th>
                  <th className="px-4 py-3 text-right font-medium">欠勤日数</th>
                </tr>
              </thead>
              <tbody>
                {attendanceData.map((r) => (
                  <tr key={r.employee_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3 font-mono">{r.employee_code}</td>
                    <td className="px-4 py-3">{r.employee_name}</td>
                    <td className="px-4 py-3 text-right">{r.days}日</td>
                    <td className="px-4 py-3 text-right">{Math.floor(r.total_work_minutes / 60)}h{r.total_work_minutes % 60 > 0 ? `${r.total_work_minutes % 60}m` : ""}</td>
                    <td className={`px-4 py-3 text-right ${r.total_overtime_minutes > 0 ? "text-orange-600 font-medium" : ""}`}>
                      {r.total_overtime_minutes > 0 ? `${Math.floor(r.total_overtime_minutes / 60)}h${r.total_overtime_minutes % 60 > 0 ? `${r.total_overtime_minutes % 60}m` : ""}` : "-"}
                    </td>
                    <td className="px-4 py-3 text-right">{r.paid_leave_days}日</td>
                    <td className={`px-4 py-3 text-right ${r.absent_days > 0 ? "text-red-600" : ""}`}>{r.absent_days > 0 ? `${r.absent_days}日` : "-"}</td>
                  </tr>
                ))}
                {(() => {
                  const totalDays = attendanceData.reduce((s, r) => s + r.days, 0);
                  const totalWork = attendanceData.reduce((s, r) => s + r.total_work_minutes, 0);
                  const totalOT = attendanceData.reduce((s, r) => s + r.total_overtime_minutes, 0);
                  const totalPaid = attendanceData.reduce((s, r) => s + r.paid_leave_days, 0);
                  const totalAbsent = attendanceData.reduce((s, r) => s + r.absent_days, 0);
                  return (
                    <tr className="border-t-2 bg-muted/30 font-bold">
                      <td className="px-4 py-3">合計</td>
                      <td />
                      <td className="px-4 py-3 text-right">{totalDays}日</td>
                      <td className="px-4 py-3 text-right">{Math.floor(totalWork / 60)}h{totalWork % 60 > 0 ? `${totalWork % 60}m` : ""}</td>
                      <td className="px-4 py-3 text-right text-orange-600">{totalOT > 0 ? `${Math.floor(totalOT / 60)}h${totalOT % 60 > 0 ? `${totalOT % 60}m` : ""}` : "-"}</td>
                      <td className="px-4 py-3 text-right">{totalPaid}日</td>
                      <td className="px-4 py-3 text-right">{totalAbsent}日</td>
                    </tr>
                  );
                })()}
              </tbody>
            </table>
          </div>
        )}

        {attendanceData && attendanceData.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
            <Clock className="mb-3 h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">該当月の勤怠データがありません。</p>
          </div>
        )}

        {expenseData && expenseData.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <div className="border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">経費精算一覧</h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/30">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">精算日</th>
                  <th className="px-4 py-3 text-left font-medium">タイトル</th>
                  <th className="px-4 py-3 text-left font-medium">従業員</th>
                  <th className="px-4 py-3 text-right font-medium">金額</th>
                  <th className="px-4 py-3 text-center font-medium">ステータス</th>
                </tr>
              </thead>
              <tbody>
                {expenseData.map((r) => (
                  <tr key={r.report_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3">{r.report_date}</td>
                    <td className="px-4 py-3 font-medium">{r.title}</td>
                    <td className="px-4 py-3">{r.employee_name || "-"}</td>
                    <td className="px-4 py-3 text-right font-medium">¥{parseInt(r.total_amount).toLocaleString()}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`rounded px-2 py-0.5 text-xs ${
                        r.status === "submitted" ? "bg-yellow-100 text-yellow-700" :
                        r.status === "approved" ? "bg-green-100 text-green-700" :
                        r.status === "rejected" ? "bg-red-100 text-red-700" :
                        r.status === "paid" ? "bg-blue-100 text-blue-700" :
                        "bg-gray-100 text-gray-700"
                      }`}>
                        {r.status === "submitted" ? "申請中" : r.status === "approved" ? "承認済" : r.status === "rejected" ? "差戻し" : r.status === "paid" ? "支払済" : r.status}
                      </span>
                    </td>
                  </tr>
                ))}
                {(() => {
                  const total = expenseData.reduce((s, r) => s + parseInt(r.total_amount), 0);
                  return (
                    <tr className="border-t-2 bg-muted/30 font-bold">
                      <td className="px-4 py-3">合計</td>
                      <td colSpan={2} />
                      <td className="px-4 py-3 text-right">¥{total.toLocaleString()}</td>
                      <td />
                    </tr>
                  );
                })()}
              </tbody>
            </table>
          </div>
        )}

        {expenseData && expenseData.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
            <Wallet className="mb-3 h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">経費精算データがありません。</p>
          </div>
        )}

        {incomeData && (
          <div className="overflow-x-auto rounded-lg border">
            <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">損益計算書（P/L） — {incomeData.as_of}</h2>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${parseFloat(incomeData.net_income) >= 0 ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                {parseFloat(incomeData.net_income) >= 0 ? "黒字" : "赤字"}
              </span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                <tr className="border-b bg-muted/30">
                  <td className="px-4 py-2 font-bold" colSpan={3}>収益</td>
                </tr>
                {incomeData.revenues.map((r) => (
                  <tr key={r.account_code} className="border-t">
                    <td className="px-4 py-2 font-mono text-muted-foreground">{r.account_code}</td>
                    <td className="px-4 py-2">{r.account_name}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-muted/20 font-bold">
                  <td className="px-4 py-2" colSpan={2}>収益合計</td>
                  <td className="px-4 py-2 text-right text-blue-600">¥{parseInt(incomeData.total_revenue).toLocaleString()}</td>
                </tr>
                <tr className="border-b bg-muted/30">
                  <td className="px-4 py-2 font-bold" colSpan={3}>費用</td>
                </tr>
                {incomeData.expenses.map((r) => (
                  <tr key={r.account_code} className="border-t">
                    <td className="px-4 py-2 font-mono text-muted-foreground">{r.account_code}</td>
                    <td className="px-4 py-2">{r.account_name}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-muted/20 font-bold">
                  <td className="px-4 py-2" colSpan={2}>費用合計</td>
                  <td className="px-4 py-2 text-right text-red-600">¥{parseInt(incomeData.total_expense).toLocaleString()}</td>
                </tr>
                <tr className="border-t-2 bg-primary/10 font-bold text-base">
                  <td className="px-4 py-3" colSpan={2}>当期純利益</td>
                  <td className={`px-4 py-3 text-right ${parseFloat(incomeData.net_income) >= 0 ? "text-green-700" : "text-red-700"}`}>
                    ¥{parseInt(incomeData.net_income).toLocaleString()}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {balanceData && (
          <div className="overflow-x-auto rounded-lg border">
            <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-3">
              <h2 className="text-lg font-semibold">貸借対照表（B/S） — {balanceData.as_of}</h2>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${balanceData.is_balanced ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                {balanceData.is_balanced ? "貸借一致" : "貸借不一致"}
              </span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                <tr className="border-b bg-muted/30">
                  <td className="px-4 py-2 font-bold" colSpan={3}>資産</td>
                </tr>
                {balanceData.assets.map((r) => (
                  <tr key={r.account_code} className="border-t">
                    <td className="px-4 py-2 font-mono text-muted-foreground">{r.account_code}</td>
                    <td className="px-4 py-2">{r.account_name}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-muted/20 font-bold">
                  <td className="px-4 py-2" colSpan={2}>資産合計</td>
                  <td className="px-4 py-2 text-right text-blue-600">¥{parseInt(balanceData.total_assets).toLocaleString()}</td>
                </tr>
                <tr className="border-b bg-muted/30">
                  <td className="px-4 py-2 font-bold" colSpan={3}>負債</td>
                </tr>
                {balanceData.liabilities.map((r) => (
                  <tr key={r.account_code} className="border-t">
                    <td className="px-4 py-2 font-mono text-muted-foreground">{r.account_code}</td>
                    <td className="px-4 py-2">{r.account_name}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-muted/20 font-bold">
                  <td className="px-4 py-2" colSpan={2}>負債合計</td>
                  <td className="px-4 py-2 text-right text-orange-600">¥{parseInt(balanceData.total_liabilities).toLocaleString()}</td>
                </tr>
                <tr className="border-b bg-muted/30">
                  <td className="px-4 py-2 font-bold" colSpan={3}>純資産</td>
                </tr>
                {balanceData.equity.map((r) => (
                  <tr key={r.account_code} className="border-t">
                    <td className="px-4 py-2 font-mono text-muted-foreground">{r.account_code}</td>
                    <td className="px-4 py-2">{r.account_name}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(r.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-muted/20 font-bold">
                  <td className="px-4 py-2" colSpan={2}>純資産合計</td>
                  <td className="px-4 py-2 text-right text-purple-600">¥{parseInt(balanceData.total_equity).toLocaleString()}</td>
                </tr>
                <tr className="border-t-2 bg-primary/10 font-bold text-base">
                  <td className="px-4 py-3">負債 + 純資産</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">合計</td>
                  <td className="px-4 py-3 text-right">¥{(parseInt(balanceData.total_liabilities) + parseInt(balanceData.total_equity)).toLocaleString()}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {cashFlowData && (
          <div className="mt-6 overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-primary/10">
                <tr>
                  <th className="px-4 py-3 text-left">区分</th>
                  <th className="px-4 py-3 text-left">項目</th>
                  <th className="px-4 py-3 text-right">金額</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t-2 bg-blue-50/50">
                  <td className="px-4 py-2 font-bold text-blue-700" rowSpan={cashFlowData.operating.items.length + 1}>営業CF</td>
                </tr>
                {cashFlowData.operating.items.map((item: { item: string; amount: string }, i: number) => (
                  <tr key={`op-${i}`} className="border-t">
                    <td className="px-4 py-2" colSpan={1}>{item.item}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(item.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-blue-100/50 font-bold">
                  <td className="px-4 py-2">営業CF小計</td>
                  <td className="px-4 py-2 text-right text-blue-700">¥{parseInt(cashFlowData.operating.subtotal).toLocaleString()}</td>
                </tr>
                <tr className="border-t-2 bg-green-50/50">
                  <td className="px-4 py-2 font-bold text-green-700" rowSpan={cashFlowData.investing.items.length + 1}>投資CF</td>
                </tr>
                {cashFlowData.investing.items.map((item: { item: string; amount: string }, i: number) => (
                  <tr key={`inv-${i}`} className="border-t">
                    <td className="px-4 py-2">{item.item}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(item.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-green-100/50 font-bold">
                  <td className="px-4 py-2">投資CF小計</td>
                  <td className="px-4 py-2 text-right text-green-700">¥{parseInt(cashFlowData.investing.subtotal).toLocaleString()}</td>
                </tr>
                <tr className="border-t-2 bg-orange-50/50">
                  <td className="px-4 py-2 font-bold text-orange-700" rowSpan={cashFlowData.financing.items.length + 1}>財務CF</td>
                </tr>
                {cashFlowData.financing.items.map((item: { item: string; amount: string }, i: number) => (
                  <tr key={`fin-${i}`} className="border-t">
                    <td className="px-4 py-2">{item.item}</td>
                    <td className="px-4 py-2 text-right">¥{parseInt(item.amount).toLocaleString()}</td>
                  </tr>
                ))}
                <tr className="border-t bg-orange-100/50 font-bold">
                  <td className="px-4 py-2">財務CF小計</td>
                  <td className="px-4 py-2 text-right text-orange-700">¥{parseInt(cashFlowData.financing.subtotal).toLocaleString()}</td>
                </tr>
                <tr className="border-t-2 bg-primary/10 font-bold text-base">
                  <td className="px-4 py-3" colSpan={2}>現金及び現金同等物の純増減</td>
                  <td className="px-4 py-3 text-right">¥{parseInt(cashFlowData.net_cash_flow).toLocaleString()}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-8 rounded-lg border bg-card p-6">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
            <Lock className="h-5 w-5 text-orange-600" />
            月次締切（{new Date().getFullYear()}年）
          </h2>
          <button
            onClick={fetchPeriodCloses}
            disabled={!companyId}
            className="mb-4 flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            <RefreshCw className="h-4 w-4" />
            更新
          </button>
          {periodCloses.length > 0 ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => {
                const close = periodCloses.find((c) => c.month === m);
                const isClosed = close?.status === "closed";
                return (
                  <div
                    key={m}
                    className={`rounded-md border p-3 text-center ${isClosed ? "border-green-500/50 bg-green-50" : "border-muted bg-muted/30"}`}
                  >
                    <p className="mb-2 text-sm font-bold">{m}月</p>
                    <p className={`mb-2 text-xs ${isClosed ? "text-green-700" : "text-muted-foreground"}`}>
                      {isClosed ? "締切済" : "未締切"}
                    </p>
                    <button
                      onClick={() => handlePeriodClose(m, isClosed ? "reopen" : "close")}
                      disabled={closeLoading === `${m}-${isClosed ? "reopen" : "close"}`}
                      className={`flex items-center justify-center gap-1 rounded px-2 py-1 text-xs font-medium disabled:opacity-50 ${
                        isClosed ? "bg-yellow-100 text-yellow-700 hover:bg-yellow-200" : "bg-primary/10 text-primary hover:bg-primary/20"
                      }`}
                    >
                      {closeLoading === `${m}-${isClosed ? "reopen" : "close"}` ? <Loader2 className="h-3 w-3 animate-spin" /> : isClosed ? <LockOpen className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
                      {isClosed ? "再開" : "締切"}
                    </button>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">締切データがありません。「更新」ボタンで再取得できます。</p>
          )}
        </div>
    </PageLayout>
  );
}
