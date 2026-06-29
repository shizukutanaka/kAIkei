"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { Receipt, Clock, Sparkles, AlertCircle, TrendingUp, BookOpen, Calculator, FileCheck, Users, Handshake, Gift, CalendarClock } from "lucide-react";
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

  useEffect(() => {
    if (!companyId) {
      setLoading(false);
      return;
    }
    setLoading(true);

    const fetchDashboard = async () => {
      try {
        const [journals, accounts, assets, employees, partners, payrollRecs, bonusRecs, yearEndRecs] = await Promise.allSettled([
          apiGet<JournalList>("/journals", { company_id: companyId, page: "1", page_size: "200" }),
          apiGet<unknown[]>("/masters", { company_id: companyId }),
          apiGet<unknown[]>("/fixed-assets", { company_id: companyId }),
          apiGet<unknown[]>("/payroll/employees", { company_id: companyId }),
          apiGet<unknown[]>("/partners", { company_id: companyId }),
          apiGet<Array<{ total_gross: string; net_pay: string; status: string }>>("/payroll/records", {
            company_id: companyId,
            payroll_year: new Date().getFullYear().toString(),
            payroll_month: (new Date().getMonth() + 1).toString(),
          }),
          apiGet<Array<{ bonus_amount: string; net_pay: string; status: string }>>("/bonus/records", {
            company_id: companyId,
            bonus_year: new Date().getFullYear().toString(),
            bonus_term: "summer",
          }),
          apiGet<Array<{ total_gross: string; adjustment_amount: string; status: string }>>("/year-end/records", {
            company_id: companyId,
            adjustment_year: new Date().getFullYear().toString(),
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
        if (employees.status === "fulfilled" && Array.isArray(employees.value)) {
          next.employeeCount = employees.value.length;
        }
        if (partners.status === "fulfilled" && Array.isArray(partners.value)) {
          next.partnerCount = partners.value.length;
        }
        if (payrollRecs.status === "fulfilled" && Array.isArray(payrollRecs.value) && payrollRecs.value.length > 0) {
          setPayrollSummary({
            count: payrollRecs.value.length,
            totalGross: payrollRecs.value.reduce((s, r) => s + parseFloat(r.total_gross), 0),
            totalNet: payrollRecs.value.reduce((s, r) => s + parseFloat(r.net_pay), 0),
            status: payrollRecs.value[0].status,
          });
        } else {
          setPayrollSummary(null);
        }
        if (bonusRecs.status === "fulfilled" && Array.isArray(bonusRecs.value) && bonusRecs.value.length > 0) {
          setBonusSummary({
            count: bonusRecs.value.length,
            totalGross: bonusRecs.value.reduce((s, r) => s + parseFloat(r.bonus_amount), 0),
            totalNet: bonusRecs.value.reduce((s, r) => s + parseFloat(r.net_pay), 0),
            status: bonusRecs.value[0].status,
          });
        } else {
          setBonusSummary(null);
        }
        if (yearEndRecs.status === "fulfilled" && Array.isArray(yearEndRecs.value) && yearEndRecs.value.length > 0) {
          setYearEndSummary({
            count: yearEndRecs.value.length,
            totalGross: yearEndRecs.value.reduce((s, r) => s + parseFloat(r.total_gross), 0),
            totalAdjustment: yearEndRecs.value.reduce((s, r) => s + parseFloat(r.adjustment_amount), 0),
            status: yearEndRecs.value[0].status,
          });
        } else {
          setYearEndSummary(null);
        }

        setData(next);
      } catch {
        // API not running
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, [companyId]);

  const cards = [
    { label: "仕訳数", value: data.journalCount, icon: Receipt, color: "text-blue-600" },
    { label: "未承認", value: data.pendingApprovals, icon: Clock, color: "text-yellow-600" },
    { label: "承認済", value: data.approvedCount, icon: FileCheck, color: "text-green-600" },
    { label: "下書き", value: data.draftCount, icon: AlertCircle, color: "text-gray-600" },
    { label: "勘定科目", value: data.accountCount, icon: BookOpen, color: "text-indigo-600" },
    { label: "固定資産", value: data.assetCount, icon: Calculator, color: "text-purple-600" },
    { label: "従業員", value: data.employeeCount, icon: Users, color: "text-cyan-600" },
    { label: "取引先", value: data.partnerCount, icon: Handshake, color: "text-orange-600" },
  ];

  if (loading || userLoading) {
    return (
      <PageLayout>
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
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">ダッシュボード</h1>
          {user && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{user.display_name}</span>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                {user.role}
              </span>
            </div>
          )}
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
              <div key={card.label} className="rounded-lg border bg-card p-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">{card.label}</p>
                  <Icon className={`h-5 w-5 ${card.color}`} />
                </div>
                <p className="mt-2 text-3xl font-bold">{card.value}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <TrendingUp className="h-5 w-5 text-primary" />
              仕訳ステータス
            </h2>
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
                <span className="flex items-center gap-1 text-xs text-green-600">
                  <span className="h-2 w-2 rounded-full bg-green-500" />
                  稼働中
                </span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">データベース</span>
                <span className="flex items-center gap-1 text-xs text-green-600">
                  <span className="h-2 w-2 rounded-full bg-green-500" />
                  接続済
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
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <Users className="h-5 w-5 text-cyan-600" />
              当月の給与サマリー
            </h2>
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
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <Gift className="h-5 w-5 text-purple-600" />
              賞与サマリー（夏季）
            </h2>
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
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
            <CalendarClock className="h-5 w-5 text-indigo-600" />
            年末調整サマリー（{new Date().getFullYear()}年）
          </h2>
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
    </PageLayout>
  );
}
