"use client";

import { useState } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { FileText, Search } from "lucide-react";

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

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  asset: "資産",
  liability: "負債",
  equity: "純資産",
  revenue: "収益",
  expense: "費用",
};

export default function ReportsPage() {
  const [companyId, setCompanyId] = useState("");
  const [asOf, setAsOf] = useState(new Date().toISOString().split("T")[0]);
  const [reportType, setReportType] = useState<"trial-balance" | "monthly">("trial-balance");
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [month, setMonth] = useState((new Date().getMonth() + 1).toString());
  const [data, setData] = useState<TrialBalance | null>(null);
  const [monthlyData, setMonthlyData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleFetch = async () => {
    if (!companyId) {
      setError("会社IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    setMonthlyData(null);

    try {
      if (reportType === "trial-balance") {
        const result = await apiGet<TrialBalance>("/reports/trial-balance", {
          company_id: companyId,
          as_of: asOf,
        });
        setData(result);
      } else {
        const result = await apiGet<Record<string, unknown>>("/reports/monthly-balances", {
          company_id: companyId,
          year,
          month,
        });
        setMonthlyData(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
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
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">会社ID</label>
              <input
                type="text"
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
                placeholder="UUID"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
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
          </div>

          <button
            onClick={handleFetch}
            disabled={loading}
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
