"use client";

import { useState } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { formatYen } from "@/lib/format";
import { Landmark, Search, Loader2, TrendingUp, TrendingDown } from "lucide-react";

interface Bucket {
  horizon_days: number;
  inflows: string;
  outflows: string;
  net_cashflow: string;
}

interface CashflowForecast {
  company_id: string;
  as_of: string;
  buckets: Bucket[];
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function TreasuryPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("report:read") ?? false;

  const [asOf, setAsOf] = useState(todayISO());
  const [forecast, setForecast] = useState<CashflowForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleForecast = async () => {
    if (!companyId || !asOf) {
      setError("基準日を指定してください。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<CashflowForecast>("/treasury/cashflow-forecast", {
        company_id: companyId,
        as_of: asOf,
      });
      setForecast(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "資金繰り予測の取得に失敗しました");
      setForecast(null);
    } finally {
      setLoading(false);
    }
  };

  if (!canRead) {
    return (
      <PageLayout title="資金繰り予測">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（report:read が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="資金繰り予測">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Landmark className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">発行済み請求書（入金予定）と承認済み支払申請（出金予定）から、基準日以降の期間別キャッシュフローを予測します。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}

        <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
          <div>
            <label htmlFor="as-of" className="mb-1 block text-xs font-medium">基準日</label>
            <input id="as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="rounded-md border px-3 py-2 text-sm" />
          </div>
          <button type="button" onClick={handleForecast} disabled={loading} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />} 予測
          </button>
        </div>

        {forecast && (
          <section aria-labelledby="forecast-heading">
            <h2 id="forecast-heading" className="mb-2 text-sm font-semibold">
              予測結果（基準日 {forecast.as_of}）
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {forecast.buckets.map((b) => {
                const net = Number(b.net_cashflow);
                return (
                  <div key={b.horizon_days} className="rounded-lg border p-4">
                    <p className="text-xs text-muted-foreground">今後 {b.horizon_days} 日</p>
                    <p className={`mt-1 flex items-center gap-1 text-lg font-semibold tabular-nums ${net < 0 ? "text-destructive" : "text-green-700"}`}>
                      {net < 0 ? <TrendingDown className="h-4 w-4" aria-hidden="true" /> : <TrendingUp className="h-4 w-4" aria-hidden="true" />}
                      {formatYen(b.net_cashflow)}
                    </p>
                    <dl className="mt-2 space-y-1 text-xs text-muted-foreground">
                      <div className="flex justify-between"><dt>入金</dt><dd className="tabular-nums text-foreground">{formatYen(b.inflows)}</dd></div>
                      <div className="flex justify-between"><dt>出金</dt><dd className="tabular-nums text-foreground">{formatYen(b.outflows)}</dd></div>
                    </dl>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <caption className="sr-only">期間別キャッシュフロー予測</caption>
                <thead className="bg-muted/50">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left font-medium">期間</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">入金予定</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">出金予定</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">純キャッシュフロー</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.buckets.map((b) => {
                    const net = Number(b.net_cashflow);
                    return (
                      <tr key={b.horizon_days} className={`border-t ${net < 0 ? "bg-destructive/5" : ""}`}>
                        <td className="px-3 py-2">今後 {b.horizon_days} 日</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatYen(b.inflows)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatYen(b.outflows)}</td>
                        <td className={`px-3 py-2 text-right tabular-nums ${net < 0 ? "text-destructive" : ""}`}>{formatYen(b.net_cashflow)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </PageLayout>
  );
}
