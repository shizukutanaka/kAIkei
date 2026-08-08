"use client";

import { useState, useCallback } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { formatYen } from "@/lib/format";
import { Clock, Search, Loader2, AlertTriangle } from "lucide-react";

interface BucketAmounts {
  not_due: string;
  overdue_1_30: string;
  overdue_31_60: string;
  overdue_61_90: string;
  overdue_over_90: string;
}

interface PartnerLine {
  partner_id: string | null;
  partner_name: string;
  buckets: BucketAmounts;
  total: string;
  invoice_count: number;
  oldest_days_overdue: number;
}

interface ArAging {
  company_id: string;
  as_of: string;
  buckets: BucketAmounts;
  total: string;
  overdue_total: string;
  invoice_count: number;
  partners: PartnerLine[];
}

const BUCKETS: { key: keyof BucketAmounts; label: string }[] = [
  { key: "not_due", label: "期日未到来" },
  { key: "overdue_1_30", label: "1-30日超過" },
  { key: "overdue_31_60", label: "31-60日超過" },
  { key: "overdue_61_90", label: "61-90日超過" },
  { key: "overdue_over_90", label: "90日超過" },
];

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ArAgingPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("report:read") ?? false;

  const [asOf, setAsOf] = useState(todayISO());
  const [data, setData] = useState<ArAging | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const result = await apiGet<ArAging>("/reports/ar-aging", { company_id: companyId, as_of: asOf });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "債権年齢表の取得に失敗しました");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [companyId, asOf]);

  if (!canRead) {
    return (
      <PageLayout title="債権年齢表">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（report:read が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="債権年齢表">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Clock className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">未回収（発行済み）の請求書を支払期日からの経過日数で区分し、取引先別に集計します。滞留債権の回収管理や貸倒引当金の見積り基礎資料に利用できます。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}

        <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
          <div>
            <label htmlFor="ar-as-of" className="mb-1 block text-xs font-medium">基準日</label>
            <input id="ar-as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="rounded-md border px-3 py-2 text-sm" />
          </div>
          <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />} 集計
          </button>
        </div>

        {data && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border p-4">
                <p className="text-xs text-muted-foreground">債権残高合計</p>
                <p className="text-lg font-semibold tabular-nums">{formatYen(data.total)}</p>
              </div>
              <div className={`rounded-lg border p-4 ${Number(data.overdue_total) > 0 ? "border-amber-500/40 bg-amber-50" : ""}`}>
                <p className="text-xs text-muted-foreground">延滞合計</p>
                <p className={`text-lg font-semibold tabular-nums ${Number(data.overdue_total) > 0 ? "text-amber-700" : ""}`}>{formatYen(data.overdue_total)}</p>
              </div>
              <div className={`rounded-lg border p-4 ${Number(data.buckets.overdue_over_90) > 0 ? "border-destructive/40 bg-destructive/10" : ""}`}>
                <p className="text-xs text-muted-foreground">90日超（要注意）</p>
                <p className={`text-lg font-semibold tabular-nums ${Number(data.buckets.overdue_over_90) > 0 ? "text-destructive" : ""}`}>{formatYen(data.buckets.overdue_over_90)}</p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-xs text-muted-foreground">対象請求書数</p>
                <p className="text-lg font-semibold tabular-nums">{data.invoice_count}</p>
              </div>
            </div>

            {data.partners.length === 0 ? (
              <p className="text-sm text-muted-foreground">未回収の請求書はありません。</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <caption className="sr-only">取引先別の債権年齢表（基準日 {data.as_of}）</caption>
                  <thead className="bg-muted/50">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-medium">取引先</th>
                      {BUCKETS.map((b) => (
                        <th key={b.key} scope="col" className="px-3 py-2 text-right font-medium">{b.label}</th>
                      ))}
                      <th scope="col" className="px-3 py-2 text-right font-medium">合計</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">最長延滞</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.partners.map((p) => (
                      <tr key={p.partner_id ?? "none"} className={`border-t ${Number(p.buckets.overdue_over_90) > 0 ? "bg-destructive/5" : ""}`}>
                        <td className="px-3 py-2">
                          {p.partner_name}
                          <span className="ml-1 text-xs text-muted-foreground">({p.invoice_count}件)</span>
                        </td>
                        {BUCKETS.map((b) => (
                          <td key={b.key} className={`px-3 py-2 text-right tabular-nums ${b.key === "overdue_over_90" && Number(p.buckets[b.key]) > 0 ? "text-destructive" : ""}`}>
                            {Number(p.buckets[b.key]) === 0 ? "-" : formatYen(p.buckets[b.key])}
                          </td>
                        ))}
                        <td className="px-3 py-2 text-right font-medium tabular-nums">{formatYen(p.total)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {p.oldest_days_overdue > 0 ? (
                            <span className={p.oldest_days_overdue > 90 ? "inline-flex items-center gap-1 text-destructive" : ""}>
                              {p.oldest_days_overdue > 90 && <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
                              {p.oldest_days_overdue}日
                            </span>
                          ) : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="border-t-2 bg-muted/30 font-medium">
                    <tr>
                      <th scope="row" className="px-3 py-2 text-left">合計</th>
                      {BUCKETS.map((b) => (
                        <td key={b.key} className="px-3 py-2 text-right tabular-nums">{formatYen(data.buckets[b.key])}</td>
                      ))}
                      <td className="px-3 py-2 text-right tabular-nums">{formatYen(data.total)}</td>
                      <td className="px-3 py-2" />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </PageLayout>
  );
}
