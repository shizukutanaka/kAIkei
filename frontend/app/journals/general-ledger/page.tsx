"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { BookOpen, RefreshCw, Download } from "lucide-react";
import { useToast } from "@/components/toast";
import { SkeletonTable } from "@/components/skeleton";

interface GeneralLedgerEntry {
  date: string;
  journal_number: string;
  summary: string;
  debit_credit: string;
  amount: string;
  description: string;
}

interface GeneralLedgerAccount {
  account_code: string;
  account_name: string;
  account_type: string;
  opening_balance: string;
  total_debit: string;
  total_credit: string;
  closing_balance: string;
  entries: GeneralLedgerEntry[];
}

interface GeneralLedger {
  start_date: string;
  end_date: string;
  accounts: GeneralLedgerAccount[];
}

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  asset: "資産",
  liability: "負債",
  equity: "純資産",
  revenue: "収益",
  expense: "費用",
};

export default function GeneralLedgerPage() {
  const { companyId } = useCompany();
  const { toast } = useToast();
  const [data, setData] = useState<GeneralLedger | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [startDate, setStartDate] = useState(`${new Date().getFullYear()}-01-01`);
  const [endDate, setEndDate] = useState(new Date().toISOString().split("T")[0]);
  const [accountCode, setAccountCode] = useState("");
  const [expandedAccount, setExpandedAccount] = useState<string | null>(null);

  const handleFetch = async () => {
    if (!companyId) {
      setError("サイドバーで会社IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    try {
      const params: Record<string, string> = {
        company_id: companyId,
        start_date: startDate,
        end_date: endDate,
      };
      if (accountCode) params.account_code = accountCode;
      const result = await apiGet<GeneralLedger>("/journals/general-ledger", params);
      setData(result);
      toast("総勘定元帳を取得しました", "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) handleFetch();
  }, [companyId]);

  const handleExportCSV = async () => {
    if (!companyId) return;
    try {
      const params: Record<string, string> = {
        company_id: companyId,
        start_date: startDate,
        end_date: endDate,
      };
      if (accountCode) params.account_code = accountCode;
      const csv = await apiGet<string>("/journals/general-ledger/export", params);
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `general_ledger_${startDate}_${endDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("総勘定元帳CSVを出力しました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "CSV出力に失敗しました", "error");
    }
  };

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <BookOpen className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">総勘定元帳</h1>
      </div>

      <div className="mb-6 rounded-lg border bg-card p-4">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium">開始日</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">終了日</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">科目コード（任意）</label>
            <input
              type="text"
              value={accountCode}
              onChange={(e) => setAccountCode(e.target.value)}
              placeholder="例: 1000"
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          </div>
        </div>
        <div className="mt-4 flex gap-2">
          <button
            onClick={handleFetch}
            disabled={loading || !companyId}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "取得中..." : "更新"}
          </button>
          <button
            onClick={handleExportCSV}
            disabled={!companyId || !data}
            className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            CSV出力
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && <SkeletonTable rows={5} columns={6} />}

      {data && (
        <div className="space-y-4">
          {data.accounts.length === 0 ? (
            <p className="text-sm text-muted-foreground">該当期間の取引データがありません</p>
          ) : (
            <>
            <p className="mb-2 text-xs text-muted-foreground">{data.accounts.length}科目</p>
            {data.accounts.map((acct) => {
              const isExpanded = expandedAccount === acct.account_code;
              return (
                <div key={acct.account_code} className="overflow-hidden rounded-lg border">
                  <button
                    onClick={() => setExpandedAccount(isExpanded ? null : acct.account_code)}
                    className="flex w-full items-center justify-between bg-primary/5 px-4 py-3 text-left"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm font-bold">{acct.account_code}</span>
                      <span className="text-sm font-medium">{acct.account_name}</span>
                      <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        {ACCOUNT_TYPE_LABELS[acct.account_type] || acct.account_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-6 text-sm">
                      <span className="text-muted-foreground">期首: ¥{parseInt(acct.opening_balance).toLocaleString()}</span>
                      <span className="text-blue-600">借方: ¥{parseInt(acct.total_debit).toLocaleString()}</span>
                      <span className="text-orange-600">貸方: ¥{parseInt(acct.total_credit).toLocaleString()}</span>
                      <span className="font-bold">期末: ¥{parseInt(acct.closing_balance).toLocaleString()}</span>
                      <span className="text-muted-foreground">{isExpanded ? "▼" : "▶"}</span>
                    </div>
                  </button>
                  {isExpanded && (
                    <table className="w-full text-sm">
                      <thead className="bg-muted/30">
                        <tr>
                          <th className="px-4 py-2 text-left">取引日</th>
                          <th className="px-4 py-2 text-left">伝票No</th>
                          <th className="px-4 py-2 text-left">摘要</th>
                          <th className="px-4 py-2 text-right">借方</th>
                          <th className="px-4 py-2 text-right">貸方</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t bg-muted/10">
                          <td className="px-4 py-2 text-muted-foreground" colSpan={3}>期首残高</td>
                          <td className="px-4 py-2 text-right text-muted-foreground" colSpan={2}>¥{parseInt(acct.opening_balance).toLocaleString()}</td>
                        </tr>
                        {acct.entries.map((entry, i) => (
                          <tr key={i} className="border-t">
                            <td className="px-4 py-2">{entry.date}</td>
                            <td className="px-4 py-2 font-mono text-xs">{entry.journal_number}</td>
                            <td className="px-4 py-2">{entry.summary || entry.description}</td>
                            <td className="px-4 py-2 text-right text-blue-600">
                              {entry.debit_credit === "debit" ? `¥${parseInt(entry.amount).toLocaleString()}` : ""}
                            </td>
                            <td className="px-4 py-2 text-right text-orange-600">
                              {entry.debit_credit === "credit" ? `¥${parseInt(entry.amount).toLocaleString()}` : ""}
                            </td>
                          </tr>
                        ))}
                        <tr className="border-t-2 bg-primary/5 font-bold">
                          <td className="px-4 py-2" colSpan={3}>期末残高</td>
                          <td className="px-4 py-2 text-right" colSpan={2}>¥{parseInt(acct.closing_balance).toLocaleString()}</td>
                        </tr>
                      </tbody>
                    </table>
                  )}
                </div>
              );
            })}
            </>
          )}
        </div>
      )}
    </PageLayout>
  );
}
