"use client";

import { useState, useEffect, useCallback } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { Receipt, Clock, Sparkles, AlertCircle, TrendingUp, BookOpen, Calculator, FileCheck, Users, Handshake, Gift, CalendarClock, Wallet, FilePlus, Landmark, TrendingDown, RefreshCw, ArrowRight } from "lucide-react";
import Link from "next/link";
import { SkeletonCard } from "@/components/skeleton";

interface JournalList {
  items: Array<{ approval_status: string }>;
  total: number;
  page: number;
  page_size: number;
}

interface DashboardData {
  journalCount: number;
  pendingApprovals: number;
  approvedCount: number;
  draftCount: number;
  accountCount: number;
  assetCount: number;
  employeeCount: number;
  partnerCount: number;
}

interface PayrollSummary {
  count: number;
  totalGross: number;
  totalNet: number;
  status: string | null;
}

interface BonusSummary {
  count: number;
  totalGross: number;
  totalNet: number;
  status: string | null;
}

interface YearEndSummary {
  count: number;
  totalGross: number;
  totalAdjustment: number;
  status: string | null;
}

interface AttendanceSummary {
  count: number;
  totalWorkMinutes: number;
  totalOvertimeMinutes: number;
  paidLeaveDays: number;
  absentDays: number;
}

interface ExpenseSummary {
  count: number;
  totalAmount: number;
  pendingCount: number;
  approvedCount: number;
}

interface InvoiceSummary {
  count: number;
  totalSubtotal: number;
  totalTax: number;
  totalAmount: number;
  draftCount: number;
  issuedCount: number;
  paidCount: number;
}

interface TaxReturnSummary {
  count: number;
  totalPayable: number;
  latestYear: number | null;
  latestStatus: string | null;
}

interface PLQuickSummary {
  totalRevenue: number;
  totalExpense: number;
  netIncome: number;
}

export default function DashboardPage() {
  const { companyId } = useCompany();
  const { user, loading: userLoading } = useUser();
  const [data, setData] = useState<DashboardData>({
    journalCount: 0,
    pendingApprovals: 0,
    approvedCount: 0,
    draftCount: 0,
    accountCount: 0,
    assetCount: 0,
    employeeCount: 0,
    partnerCount: 0,
  });
  const [loading, setLoading] = useState(true);
  const [payrollSummary, setPayrollSummary] = useState<PayrollSummary | null>(null);
  const [bonusSummary, setBonusSummary] = useState<BonusSummary | null>(null);
  const [yearEndSummary, setYearEndSummary] = useState<YearEndSummary | null>(null);
  const [attendanceSummary, setAttendanceSummary] = useState<AttendanceSummary | null>(null);
  const [expenseSummary, setExpenseSummary] = useState<ExpenseSummary | null>(null);
  const [invoiceSummary, setInvoiceSummary] = useState<InvoiceSummary | null>(null);
  const [taxReturnSummary, setTaxReturnSummary] = useState<TaxReturnSummary | null>(null);
  const [plSummary, setPlSummary] = useState<PLQuickSummary | null>(null);
  const [apiStatus, setApiStatus] = useState<"ok" | "error" | "checking">("checking");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchDashboard = useCallback(async () => {
    if (!companyId) {
      setLoading(false);
      return;
    }
    setLoading(true);

    const doFetch = async () => {
      try {
        const [journals, accounts, assets, employees, partners, payrollRecs, bonusRecs, yearEndRecs, attendanceRecs, expenseRecs, invoiceStats, taxRecs, plData] = await Promise.allSettled([
          apiGet<JournalList>("/journals", { company_id: companyId, page: "1", page_size: "200" }),
          apiGet<unknown[]>("/masters", { company_id: companyId }),
          apiGet<unknown[]>("/fixed-assets", { company_id: companyId }),
          apiGet<{ items: unknown[]; total: number; page: number; page_size: number }>("/payroll/employees", { company_id: companyId }),
          apiGet<{ items: unknown[]; total: number }>("/partners", { company_id: companyId }),
          apiGet<{ items: Array<{ total_gross: string; net_pay: string; status: string }>; total: number }>("/payroll/records", {
            company_id: companyId,
            payroll_year: new Date().getFullYear().toString(),
            payroll_month: (new Date().getMonth() + 1).toString(),
          }),
          apiGet<{ items: Array<{ bonus_amount: string; net_pay: string; status: string }>; total: number; page: number; page_size: number }>("/bonus/records", {
            company_id: companyId,
            bonus_year: new Date().getFullYear().toString(),
            bonus_term: "summer",
          }),
          apiGet<{ items: Array<{ total_gross: string; adjustment_amount: string; status: string }>; total: number; page: number; page_size: number }>("/year-end/records", {
            company_id: companyId,
            adjustment_year: new Date().getFullYear().toString(),
          }),
          apiGet<Array<{ total_work_minutes: number; total_overtime_minutes: number; paid_leave_days: number; absent_days: number }>>("/attendance/summary", {
            company_id: companyId,
            year: new Date().getFullYear().toString(),
            month: (new Date().getMonth() + 1).toString(),
          }),
          apiGet<{ items: Array<{ total_amount: string; status: string }>; total: number }>("/expenses/reports", {
            company_id: companyId,
          }),
          apiGet<{ count: number; total_subtotal: string; total_tax: string; total_amount: string; draft_count: number; issued_count: number; paid_count: number; cancelled_count: number }>("/invoices/stats", {
            company_id: companyId,
            year: new Date().getFullYear().toString(),
          }),
          apiGet<{ items: Array<{ tax_year: number; tax_payable: string; status: string }>; total: number; page: number; page_size: number }>("/tax-returns/records", {
            company_id: companyId,
          }),
          apiGet<{ total_revenue: string; total_expense: string; net_income: string }>("/reports/income-statement", {
            company_id: companyId,
            as_of: new Date().toISOString().split("T")[0],
          }),
        ]);

        const next: DashboardData = {
          journalCount: 0,
          pendingApprovals: 0,
          approvedCount: 0,
          draftCount: 0,
          accountCount: 0,
          assetCount: 0,
          employeeCount: 0,
          partnerCount: 0,
        };

        if (journals.status === "fulfilled") {
          next.journalCount = journals.value.total;
          next.pendingApprovals = journals.value.items.filter((j) => j.approval_status === "submitted").length;
          next.approvedCount = journals.value.items.filter((j) => j.approval_status === "approved").length;
          next.draftCount = journals.value.items.filter((j) => j.approval_status === "draft").length;
        }
        if (accounts.status === "fulfilled" && Array.isArray(accounts.value)) {
          next.accountCount = accounts.value.length;
        }
        if (assets.status === "fulfilled" && Array.isArray(assets.value)) {
          next.assetCount = assets.value.length;
        }
        if (employees.status === "fulfilled" && employees.value?.items) {
          next.employeeCount = employees.value.items.length;
        }
        if (partners.status === "fulfilled" && partners.value?.items) {
          next.partnerCount = partners.value.items.length;
        }
        if (payrollRecs.status === "fulfilled" && payrollRecs.value?.items && payrollRecs.value.items.length > 0) {
          const items = payrollRecs.value.items;
          setPayrollSummary({
            count: items.length,
            totalGross: items.reduce((s, r) => s + parseFloat(r.total_gross), 0),
            totalNet: items.reduce((s, r) => s + parseFloat(r.net_pay), 0),
            status: items[0].status,
          });
        } else {
          setPayrollSummary(null);
        }
        if (bonusRecs.status === "fulfilled" && bonusRecs.value?.items && bonusRecs.value.items.length > 0) {
          const items = bonusRecs.value.items;
          setBonusSummary({
            count: items.length,
            totalGross: items.reduce((s, r) => s + parseFloat(r.bonus_amount), 0),
            totalNet: items.reduce((s, r) => s + parseFloat(r.net_pay), 0),
            status: items[0].status,
          });
        } else {
          setBonusSummary(null);
        }
        if (yearEndRecs.status === "fulfilled" && yearEndRecs.value?.items && yearEndRecs.value.items.length > 0) {
          const items = yearEndRecs.value.items;
          setYearEndSummary({
            count: items.length,
            totalGross: items.reduce((s, r) => s + parseFloat(r.total_gross), 0),
            totalAdjustment: items.reduce((s, r) => s + parseFloat(r.adjustment_amount), 0),
            status: items[0].status,
          });
        } else {
          setYearEndSummary(null);
        }
        if (attendanceRecs.status === "fulfilled" && Array.isArray(attendanceRecs.value) && attendanceRecs.value.length > 0) {
          setAttendanceSummary({
            count: attendanceRecs.value.length,
            totalWorkMinutes: attendanceRecs.value.reduce((s, r) => s + r.total_work_minutes, 0),
            totalOvertimeMinutes: attendanceRecs.value.reduce((s, r) => s + r.total_overtime_minutes, 0),
            paidLeaveDays: attendanceRecs.value.reduce((s, r) => s + r.paid_leave_days, 0),
            absentDays: attendanceRecs.value.reduce((s, r) => s + r.absent_days, 0),
          });
        } else {
          setAttendanceSummary(null);
        }
        if (expenseRecs.status === "fulfilled" && expenseRecs.value?.items && expenseRecs.value.items.length > 0) {
          const items = expenseRecs.value.items;
          setExpenseSummary({
            count: items.length,
            totalAmount: items.reduce((s, r) => s + parseFloat(r.total_amount), 0),
            pendingCount: items.filter((r) => r.status === "submitted").length,
            approvedCount: items.filter((r) => r.status === "approved").length,
          });
        } else {
          setExpenseSummary(null);
        }
        if (invoiceStats.status === "fulfilled" && invoiceStats.value) {
          const v = invoiceStats.value;
          setInvoiceSummary({
            count: v.count,
            totalSubtotal: parseFloat(v.total_subtotal),
            totalTax: parseFloat(v.total_tax),
            totalAmount: parseFloat(v.total_amount),
            draftCount: v.draft_count,
            issuedCount: v.issued_count,
            paidCount: v.paid_count,
          });
        } else {
          setInvoiceSummary(null);
        }
        if (taxRecs.status === "fulfilled" && taxRecs.value?.items && taxRecs.value.items.length > 0) {
          const items = taxRecs.value.items;
          const latest = items[0];
          setTaxReturnSummary({
            count: items.length,
            totalPayable: items.reduce((s, r) => s + parseFloat(r.tax_payable), 0),
            latestYear: latest.tax_year,
            latestStatus: latest.status,
          });
        } else {
          setTaxReturnSummary(null);
        }
        if (plData.status === "fulfilled" && plData.value) {
          setPlSummary({
            totalRevenue: parseFloat(plData.value.total_revenue),
            totalExpense: parseFloat(plData.value.total_expense),
            netIncome: parseFloat(plData.value.net_income),
          });
        } else {
          setPlSummary(null);
        }

        setData(next);
      } catch {
        // API not running
      } finally {
        setLoading(false);
        setLastUpdated(new Date());
      }
    };

    doFetch();
  }, [companyId]);

  useEffect(() => {
    const checkApiHealth = async () => {
      try {
        await apiGet<unknown>("/health");
        setApiStatus("ok");
      } catch {
        setApiStatus("error");
      }
    };
    checkApiHealth();
  }, []);

  const cards = [
    { label: "仕訳数", value: data.journalCount, icon: Receipt, color: "text-blue-600", href: "/journals" },
    { label: "未承認", value: data.pendingApprovals, icon: Clock, color: "text-yellow-600", href: "/approvals" },
    { label: "承認済", value: data.approvedCount, icon: FileCheck, color: "text-green-600", href: "/journals" },
    { label: "下書き", value: data.draftCount, icon: AlertCircle, color: "text-gray-600", href: "/journals" },
    { label: "勘定科目", value: data.accountCount, icon: BookOpen, color: "text-indigo-600", href: "/masters" },
    { label: "固定資産", value: data.assetCount, icon: Calculator, color: "text-purple-600", href: "/assets" },
    { label: "従業員", value: data.employeeCount, icon: Users, color: "text-cyan-600", href: "/payroll" },
    { label: "取引先", value: data.partnerCount, icon: Handshake, color: "text-orange-600", href: "/partners" },
  ];

  if (loading || userLoading) {
    return (
      <PageLayout title="ダッシュボード">
        <div className="mb-6 h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-8">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">ダッシュボード</h1>
            {lastUpdated && (
              <span className="text-xs text-muted-foreground">
                最終更新: {lastUpdated.toLocaleTimeString("ja-JP")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => fetchDashboard()}
              disabled={loading || !companyId}
              className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              更新
            </button>
            {user && (
              <>
                <span className="text-sm text-muted-foreground">{user.display_name}</span>
                <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                  {user.role}
                </span>
              </>
            )}
          </div>
        </div>

        {!companyId && (
          <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
            サイドバーで会社IDを入力してください。
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <Link
                key={card.label}
                href={card.href}
                className="rounded-lg border bg-card p-6 transition-shadow hover:shadow-md"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">{card.label}</p>
                  <Icon className={`h-5 w-5 ${card.color}`} />
                </div>
                <p className="mt-2 text-3xl font-bold">{card.value}</p>
              </Link>
            );
          })}
        </div>

        <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <TrendingUp className="h-5 w-5 text-primary" />
                仕訳ステータス
              </h2>
              <Link href="/journals" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b pb-3">
                <div className="flex items-center gap-3">
                  <Receipt className="h-4 w-4 text-blue-600" />
                  <span className="text-sm font-medium">総仕訳数</span>
                </div>
                <span className="text-lg font-bold">{data.journalCount}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <div className="flex items-center gap-3">
                  <AlertCircle className="h-4 w-4 text-gray-600" />
                  <span className="text-sm font-medium">下書き</span>
                </div>
                <span className="text-lg font-bold">{data.draftCount}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <div className="flex items-center gap-3">
                  <Clock className="h-4 w-4 text-yellow-600" />
                  <span className="text-sm font-medium">未承認</span>
                </div>
                <span className="text-lg font-bold">{data.pendingApprovals}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileCheck className="h-4 w-4 text-green-600" />
                  <span className="text-sm font-medium">承認済</span>
                </div>
                <span className="text-lg font-bold">{data.approvedCount}</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">システム状態</h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">API サーバー</span>
                <span className={`flex items-center gap-1 text-xs ${apiStatus === "ok" ? "text-green-600" : apiStatus === "error" ? "text-red-600" : "text-yellow-600"}`}>
                  <span className={`h-2 w-2 rounded-full ${apiStatus === "ok" ? "bg-green-500" : apiStatus === "error" ? "bg-red-500" : "bg-yellow-500 animate-pulse"}`} />
                  {apiStatus === "ok" ? "稼働中" : apiStatus === "error" ? "接続エラー" : "確認中..."}
                </span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">データベース</span>
                <span className={`flex items-center gap-1 text-xs ${apiStatus === "ok" ? "text-green-600" : "text-gray-500"}`}>
                  <span className={`h-2 w-2 rounded-full ${apiStatus === "ok" ? "bg-green-500" : "bg-gray-400"}`} />
                  {apiStatus === "ok" ? "接続済" : "不明"}
                </span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">AI プロバイダー</span>
                <span className="flex items-center gap-1 text-xs text-yellow-600">
                  <span className="h-2 w-2 rounded-full bg-yellow-500" />
                  未設定
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">ローカルLLM</span>
                <span className="flex items-center gap-1 text-xs text-gray-500">
                  <span className="h-2 w-2 rounded-full bg-gray-400" />
                  未接続
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Users className="h-5 w-5 text-cyan-600" />
                当月の給与サマリー
              </h2>
              <Link href="/payroll" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {payrollSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">対象人数</span>
                  <span className="text-lg font-bold">{payrollSummary.count}名</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">総支給額</span>
                  <span className="text-lg font-bold">¥{payrollSummary.totalGross.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">差引支給額</span>
                  <span className="text-lg font-bold text-green-600">¥{payrollSummary.totalNet.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">ステータス</span>
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                    {payrollSummary.status === "calculated" ? "計算済" : payrollSummary.status === "approved" ? "承認済" : payrollSummary.status === "paid" ? "支払済" : payrollSummary.status === "rejected" ? "差戻し" : payrollSummary.status}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">当月の給与データがありません。給与計算を実行してください。</p>
            )}
          </div>

          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Gift className="h-5 w-5 text-purple-600" />
                賞与サマリー（夏季）
              </h2>
              <Link href="/bonus" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {bonusSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">対象人数</span>
                  <span className="text-lg font-bold">{bonusSummary.count}名</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">賞与総額</span>
                  <span className="text-lg font-bold">¥{bonusSummary.totalGross.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">差引支給額</span>
                  <span className="text-lg font-bold text-green-600">¥{bonusSummary.totalNet.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">ステータス</span>
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                    {bonusSummary.status === "calculated" ? "計算済" : bonusSummary.status === "approved" ? "承認済" : bonusSummary.status === "paid" ? "支払済" : bonusSummary.status === "rejected" ? "差戻し" : bonusSummary.status}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">今年の夏季賞与データがありません。賞与計算を実行してください。</p>
            )}
          </div>
        </div>

        <div className="mt-8 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <CalendarClock className="h-5 w-5 text-indigo-600" />
              年末調整サマリー（{new Date().getFullYear()}年）
            </h2>
            <Link href="/year-end" className="flex items-center gap-1 text-xs text-primary hover:underline">
              詳細 <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          {yearEndSummary ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm font-medium">対象人数</span>
                <span className="text-lg font-bold">{yearEndSummary.count}名</span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm font-medium">課税対象額</span>
                <span className="text-lg font-bold">¥{yearEndSummary.totalGross.toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm font-medium">調整額合計</span>
                <span className={`text-lg font-bold ${yearEndSummary.totalAdjustment >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {yearEndSummary.totalAdjustment >= 0 ? "+" : ""}¥{yearEndSummary.totalAdjustment.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">ステータス</span>
                <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                  {yearEndSummary.status === "calculated" ? "計算済" : yearEndSummary.status === "approved" ? "確定済" : yearEndSummary.status}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">今年の年末調整データがありません。年末調整計算を実行してください。</p>
          )}
        </div>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Clock className="h-5 w-5 text-blue-600" />
                勤怠サマリー（{new Date().getFullYear()}年{new Date().getMonth() + 1}月）
              </h2>
              <Link href="/attendance" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {attendanceSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">対象人数</span>
                  <span className="text-lg font-bold">{attendanceSummary.count}名</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">総勤務時間</span>
                  <span className="text-lg font-bold">{Math.floor(attendanceSummary.totalWorkMinutes / 60)}h{attendanceSummary.totalWorkMinutes % 60 > 0 ? `${attendanceSummary.totalWorkMinutes % 60}m` : ""}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">総残業時間</span>
                  <span className={`text-lg font-bold ${attendanceSummary.totalOvertimeMinutes > 0 ? "text-orange-600" : ""}`}>
                    {attendanceSummary.totalOvertimeMinutes > 0 ? `${Math.floor(attendanceSummary.totalOvertimeMinutes / 60)}h${attendanceSummary.totalOvertimeMinutes % 60 > 0 ? `${attendanceSummary.totalOvertimeMinutes % 60}m` : ""}` : "-"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">有給・欠勤</span>
                  <span className="text-sm">
                    <span className="text-green-600 font-medium">有給{attendanceSummary.paidLeaveDays}日</span>
                    {" / "}
                    <span className="text-red-600 font-medium">欠勤{attendanceSummary.absentDays}日</span>
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">今月の勤怠データがありません。</p>
            )}
          </div>

          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Wallet className="h-5 w-5 text-purple-600" />
                経費精算サマリー
              </h2>
              <Link href="/expenses" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {expenseSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">申請件数</span>
                  <span className="text-lg font-bold">{expenseSummary.count}件</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">合計金額</span>
                  <span className="text-lg font-bold">¥{expenseSummary.totalAmount.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">承認待ち</span>
                  <span className={`text-lg font-bold ${expenseSummary.pendingCount > 0 ? "text-yellow-600" : ""}`}>{expenseSummary.pendingCount}件</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">承認済み</span>
                  <span className="text-lg font-bold text-green-600">{expenseSummary.approvedCount}件</span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">経費精算データがありません。</p>
            )}
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <FilePlus className="h-5 w-5 text-indigo-600" />
                請求書サマリー（{new Date().getFullYear()}年）
              </h2>
              <Link href="/invoices" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {invoiceSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">請求件数</span>
                  <span className="text-lg font-bold">{invoiceSummary.count}件</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">売上合計</span>
                  <span className="text-lg font-bold">¥{invoiceSummary.totalSubtotal.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">消費税合計</span>
                  <span className="text-sm font-bold text-orange-600">¥{invoiceSummary.totalTax.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">総合計</span>
                  <span className="text-lg font-bold text-primary">¥{invoiceSummary.totalAmount.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">ステータス内訳</span>
                  <span className="text-sm">
                    <span className="text-gray-600 font-medium">下書き{invoiceSummary.draftCount}</span>
                    {" / "}
                    <span className="text-blue-600 font-medium">発行済{invoiceSummary.issuedCount}</span>
                    {" / "}
                    <span className="text-green-600 font-medium">入金済{invoiceSummary.paidCount}</span>
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">今年の請求書データがありません。</p>
            )}
          </div>

          <div className="rounded-lg border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Landmark className="h-5 w-5 text-red-600" />
                消費税申告サマリー
              </h2>
              <Link href="/tax-returns" className="flex items-center gap-1 text-xs text-primary hover:underline">
                詳細 <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {taxReturnSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">申告件数</span>
                  <span className="text-lg font-bold">{taxReturnSummary.count}件</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">納付税額累計</span>
                  <span className="text-lg font-bold text-red-600">¥{taxReturnSummary.totalPayable.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm font-medium">最新年度</span>
                  <span className="text-lg font-bold">{taxReturnSummary.latestYear}年度</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">最新ステータス</span>
                  <span className={`rounded px-2 py-0.5 text-xs ${taxReturnSummary.latestStatus === "filed" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>
                    {taxReturnSummary.latestStatus === "filed" ? "申告済" : "計算済"}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">消費税申告データがありません。</p>
            )}
          </div>
        </div>

        <div className="mt-8 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              {plSummary && plSummary.netIncome >= 0 ? <TrendingUp className="h-5 w-5 text-green-600" /> : <TrendingDown className="h-5 w-5 text-red-600" />}
              損益計算書クイックサマリー（{new Date().toISOString().split("T")[0]}時点）
            </h2>
            <Link href="/reports" className="flex items-center gap-1 text-xs text-primary hover:underline">
              詳細 <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          {plSummary ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-md border bg-blue-50/50 p-4">
                <p className="mb-1 text-sm font-medium text-muted-foreground">収益合計</p>
                <p className="text-2xl font-bold text-blue-600">¥{plSummary.totalRevenue.toLocaleString()}</p>
              </div>
              <div className="rounded-md border bg-red-50/50 p-4">
                <p className="mb-1 text-sm font-medium text-muted-foreground">費用合計</p>
                <p className="text-2xl font-bold text-red-600">¥{plSummary.totalExpense.toLocaleString()}</p>
              </div>
              <div className={`rounded-md border p-4 ${plSummary.netIncome >= 0 ? "bg-green-50/50" : "bg-red-50/50"}`}>
                <p className="mb-1 text-sm font-medium text-muted-foreground">当期純利益</p>
                <p className={`text-2xl font-bold ${plSummary.netIncome >= 0 ? "text-green-700" : "text-red-700"}`}>
                  ¥{plSummary.netIncome.toLocaleString()}
                </p>
                <p className={`mt-1 text-xs ${plSummary.netIncome >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {plSummary.netIncome >= 0 ? "黒字" : "赤字"}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">損益計算書データがありません。仕訳を入力してください。</p>
          )}
        </div>
    </PageLayout>
  );
}
