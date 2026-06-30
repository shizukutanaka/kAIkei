"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { SkeletonTable } from "@/components/skeleton";
import { Calculator, Search, Download, FileCheck, X, RefreshCw, Loader2 } from "lucide-react";

interface TaxReturn {
  return_id: string;
  company_id: string;
  tax_year: number;
  filing_type: string;
  taxable_sales: string;
  non_taxable_sales: string;
  export_taxable_sales: string;
  total_sales: string;
  purchases_subject_to_tax: string;
  purchases_not_subject_to_tax: string;
  total_purchases: string;
  output_tax: string;
  input_tax: string;
  tax_adjustment: string;
  tax_payable: string;
  status: string;
  note: string | null;
}

const FILING_LABELS: Record<string, string> = {
  general: "一般課税",
  simplified: "簡易課税",
};

const STATUS_LABELS: Record<string, string> = {
  calculated: "計算済",
  filed: "申告済",
};

const STATUS_COLORS: Record<string, string> = {
  calculated: "bg-yellow-100 text-yellow-700",
  filed: "bg-green-100 text-green-700",
};

export default function TaxReturnsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const perms = user?.permissions ?? [];
  const canCreate = perms.includes("journal:create");
  const canPost = perms.includes("journal:post");

  const [records, setRecords] = useState<TaxReturn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<TaxReturn | null>(null);
  const [calcYear, setCalcYear] = useState(new Date().getFullYear().toString());
  const [filingType, setFilingType] = useState("general");
  const [taxAdjustment, setTaxAdjustment] = useState("0");
  const [calculating, setCalculating] = useState(false);
  const [transitionLoading, setTransitionLoading] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState<string | null>(null);

  const fetchRecords = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<{ items: TaxReturn[]; total: number; page: number; page_size: number }>("/tax-returns/records", { company_id: companyId });
      setRecords(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) fetchRecords();
  }, [companyId]);

  const filteredRecords = records.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return r.tax_year.toString().includes(q) || (FILING_LABELS[r.filing_type] || "").toLowerCase().includes(q);
  });

  const handleCalculate = async () => {
    if (!companyId) return;
    setCalculating(true);
    try {
      const data = await apiPost<TaxReturn>("/tax-returns/calculate", {
        company_id: companyId,
        tax_year: parseInt(calcYear),
        filing_type: filingType,
        tax_adjustment: parseFloat(taxAdjustment) || 0,
      });
      setRecords([data, ...records.filter((r) => r.return_id !== data.return_id)]);
      setSelectedRecord(data);
      toast(`${calcYear}年の消費税申告を計算しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "計算に失敗しました", "error");
    } finally {
      setCalculating(false);
    }
  };

  const handleTransition = async (returnId: string, action: "filed") => {
    const ok = await confirm({
      title: "申告完了",
      message: `${selectedRecord?.tax_year || ""}年度の消費税申告を完了しますか？`,
      confirmText: "申告完了",
      variant: "default",
    });
    if (!ok) return;
    setTransitionLoading(true);
    try {
      const data = await apiPost<TaxReturn>(
        `/tax-returns/records/${returnId}/transition?action=${action}&company_id=${companyId}`,
        {}
      );
      setRecords(records.map((r) => (r.return_id === returnId ? data : r)));
      if (selectedRecord?.return_id === returnId) setSelectedRecord(data);
      toast("申告完了にしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ステータス変更に失敗しました", "error");
    } finally {
      setTransitionLoading(false);
    }
  };

  const handleDownload = async (returnId: string, year: string) => {
    setDownloadLoading(returnId);
    try {
      const token = localStorage.getItem("token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/tax-returns/records/${returnId}/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("取得に失敗しました");
      const text = await res.text();
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tax_return_${year}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSVをダウンロードしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ダウンロードに失敗しました", "error");
    } finally {
      setDownloadLoading(null);
    }
  };

  const fmt = (v: string) => `¥${parseInt(v || "0").toLocaleString()}`;

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <Calculator className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">消費税申告</h1>
      </div>

      {!companyId && (
        <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          サイドバーで会社を選択してください。
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {canCreate && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <h2 className="mb-4 text-lg font-semibold">消費税計算</h2>
          <div className="mb-4 flex flex-wrap items-end gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">対象年度</label>
              <input type="number" value={calcYear} onChange={(e) => setCalcYear(e.target.value)} className="w-32 rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">申告区分</label>
              <select value={filingType} onChange={(e) => setFilingType(e.target.value)} className="rounded-md border px-3 py-2 text-sm">
                <option value="general">一般課税</option>
                <option value="simplified">簡易課税</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">調整額</label>
              <input type="number" value={taxAdjustment} onChange={(e) => setTaxAdjustment(e.target.value)} className="w-32 rounded-md border px-3 py-2 text-sm" />
            </div>
            <button
              onClick={handleCalculate}
              disabled={!companyId || calculating}
              className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {calculating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {calculating ? "計算中..." : "計算実行"}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            仕訳データ（承認済/記録済）から売上・仕入を集計し、消費税額を自動計算します。同年度の既存データは上書きされます。
          </p>
        </div>
      )}

      {selectedRecord && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              申告詳細 — {selectedRecord.tax_year}年度 ({FILING_LABELS[selectedRecord.filing_type]})
            </h2>
            <button onClick={() => setSelectedRecord(null)} className="rounded p-1 hover:bg-accent" aria-label="閉じる">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-3 border-b pb-2 text-sm font-semibold">売上</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>課税売上</span>
                  <span className="font-medium">{fmt(selectedRecord.taxable_sales)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>非課税売上</span>
                  <span className="font-medium">{fmt(selectedRecord.non_taxable_sales)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>輸出等免税売上</span>
                  <span className="font-medium">{fmt(selectedRecord.export_taxable_sales)}</span>
                </div>
                <div className="flex justify-between border-t pt-2 text-sm font-bold">
                  <span>売上合計</span>
                  <span>{fmt(selectedRecord.total_sales)}</span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="mb-3 border-b pb-2 text-sm font-semibold">仕入</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>課税仕入</span>
                  <span className="font-medium">{fmt(selectedRecord.purchases_subject_to_tax)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>不課税仕入</span>
                  <span className="font-medium">{fmt(selectedRecord.purchases_not_subject_to_tax)}</span>
                </div>
                <div className="flex justify-between border-t pt-2 text-sm font-bold">
                  <span>仕入合計</span>
                  <span>{fmt(selectedRecord.total_purchases)}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-lg bg-muted/30 p-4">
            <h3 className="mb-3 text-sm font-semibold">消費税額</h3>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <div className="text-center">
                <p className="text-xs text-muted-foreground">売上税額</p>
                <p className="text-lg font-bold text-blue-600">{fmt(selectedRecord.output_tax)}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">仕入税額</p>
                <p className="text-lg font-bold text-orange-600">{fmt(selectedRecord.input_tax)}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">調整額</p>
                <p className="text-lg font-bold">{fmt(selectedRecord.tax_adjustment)}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-muted-foreground">納付税額</p>
                <p className="text-xl font-bold text-primary">{fmt(selectedRecord.tax_payable)}</p>
              </div>
            </div>
          </div>

          {canPost && selectedRecord.status === "calculated" && (
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => handleTransition(selectedRecord.return_id, "filed")}
                disabled={transitionLoading}
                className="flex items-center gap-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck className="h-4 w-4" />}
                申告完了
              </button>
            </div>
          )}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="年度・申告区分で検索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-48 rounded-md border py-1.5 pl-8 pr-7 text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-accent"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
        <span className="text-xs text-muted-foreground">{filteredRecords.length}/{records.length}件</span>
        <button
          onClick={() => fetchRecords()}
          disabled={loading || !companyId}
          className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "取得中..." : "更新"}
        </button>
      </div>

      {loading ? (
        <SkeletonTable rows={5} columns={6} />
      ) : filteredRecords.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium">年度</th>
                <th className="px-4 py-3 text-left font-medium">申告区分</th>
                <th className="px-4 py-3 text-right font-medium">売上合計</th>
                <th className="px-4 py-3 text-right font-medium">仕入合計</th>
                <th className="px-4 py-3 text-right font-medium">納付税額</th>
                <th className="px-4 py-3 text-center font-medium">ステータス</th>
                <th className="px-4 py-3 text-center font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((r) => (
                <tr key={r.return_id} className="cursor-pointer border-t hover:bg-muted/30" onClick={() => setSelectedRecord(r)}>
                  <td className="px-4 py-3 font-medium">{r.tax_year}年度</td>
                  <td className="px-4 py-3">{FILING_LABELS[r.filing_type] || r.filing_type}</td>
                  <td className="px-4 py-3 text-right">{fmt(r.total_sales)}</td>
                  <td className="px-4 py-3 text-right">{fmt(r.total_purchases)}</td>
                  <td className="px-4 py-3 text-right font-bold text-primary">{fmt(r.tax_payable)}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[r.status] || "bg-gray-100 text-gray-700"}`}>
                      {STATUS_LABELS[r.status] || r.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-center gap-1">
                      <button onClick={() => setSelectedRecord(r)} className="rounded px-2 py-1 text-xs hover:bg-accent">詳細</button>
                      <button onClick={() => handleDownload(r.return_id, r.tax_year.toString())} disabled={downloadLoading === r.return_id} className="inline-flex items-center justify-center rounded p-1 hover:bg-accent disabled:opacity-50" title="CSV出力">
                        {downloadLoading === r.return_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4 text-muted-foreground" />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 bg-muted/30 font-bold">
                <td colSpan={2} className="px-4 py-3">合計</td>
                <td className="px-4 py-3 text-right">{fmt(filteredRecords.reduce((s, r) => s + parseInt(r.total_sales), 0).toString())}</td>
                <td className="px-4 py-3 text-right">{fmt(filteredRecords.reduce((s, r) => s + parseInt(r.total_purchases), 0).toString())}</td>
                <td className="px-4 py-3 text-right text-primary">{fmt(filteredRecords.reduce((s, r) => s + parseInt(r.tax_payable), 0).toString())}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <Calculator className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "消費税申告データがありません。計算を実行してください。" : "会社を選択してください。"}
          </p>
        </div>
      )}
    </PageLayout>
  );
}
