"use client";

import { useState, useRef } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPostMultipart } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Archive, Upload, Search, Loader2, CheckCircle2, ShieldCheck } from "lucide-react";

interface ArchivedDocument {
  archived_document_id: string;
  document_type: string;
  file_name: string;
  file_hash: string;
  file_size: number;
  transaction_date: string;
  amount: string | null;
  counterparty_name: string | null;
  registered_at: string;
}

const DOC_TYPES = [
  { value: "invoice", label: "請求書" },
  { value: "receipt", label: "領収書" },
  { value: "contract", label: "契約書" },
  { value: "quotation", label: "見積書" },
  { value: "other", label: "その他" },
];

function formatYen(amount: string | null): string {
  if (amount === null) return "-";
  const n = Number(amount);
  return Number.isNaN(n) ? amount : `¥${n.toLocaleString("ja-JP")}`;
}

export default function DocumentArchivePage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canManage = user?.permissions.includes("document:manage") ?? false;

  const [docs, setDocs] = useState<ArchivedDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // 取込フォーム
  const [docType, setDocType] = useState("invoice");
  const [txnDate, setTxnDate] = useState("");
  const [amount, setAmount] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // 検索3軸
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [searchCounterparty, setSearchCounterparty] = useState("");

  const handleSearch = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId, limit: "200" };
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (amountMin) params.amount_min = amountMin;
      if (amountMax) params.amount_max = amountMax;
      if (searchCounterparty) params.counterparty = searchCounterparty;
      const data = await apiGet<ArchivedDocument[]>("/documents/search", params);
      setDocs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "検索に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!companyId || !file || !txnDate) {
      setError("ファイルと取引年月日は必須です。");
      return;
    }
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.append("document_type", docType);
      form.append("transaction_date", txnDate);
      if (amount) form.append("amount", amount);
      if (counterparty) form.append("counterparty_name", counterparty);
      form.append("file", file);
      await apiPostMultipart<ArchivedDocument>("/documents", { company_id: companyId }, form);
      setNotice("証憑を登録しました（SHA-256ハッシュを付与）。");
      setTxnDate("");
      setAmount("");
      setCounterparty("");
      if (fileRef.current) fileRef.current.value = "";
      await handleSearch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setUploading(false);
    }
  };

  if (!canManage) {
    return (
      <PageLayout title="電帳法証憑アーカイブ">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（document:manage が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="電帳法証憑アーカイブ">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Archive className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">証憑をSHA-256ハッシュ付きで保存し、取引年月日・金額・取引先の3軸で検索します（電子帳簿保存法対応）。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {/* 取込フォーム */}
        <form onSubmit={handleUpload} aria-labelledby="upload-heading" className="rounded-lg border p-4">
          <h2 id="upload-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Upload className="h-4 w-4" aria-hidden="true" /> 証憑の登録
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div>
              <label htmlFor="doc-type" className="mb-1 block text-xs font-medium">書類種別</label>
              <select id="doc-type" value={docType} onChange={(e) => setDocType(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                {DOC_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="txn-date" className="mb-1 block text-xs font-medium">
                取引年月日 <span className="text-destructive" aria-hidden="true">*</span>
              </label>
              <input id="txn-date" type="date" required value={txnDate} onChange={(e) => setTxnDate(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="doc-amount" className="mb-1 block text-xs font-medium">取引金額</label>
              <input id="doc-amount" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="任意" className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="doc-counterparty" className="mb-1 block text-xs font-medium">取引先</label>
              <input id="doc-counterparty" type="text" value={counterparty} onChange={(e) => setCounterparty(e.target.value)} placeholder="任意" className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div className="lg:col-span-2">
              <label htmlFor="doc-file" className="mb-1 block text-xs font-medium">
                ファイル <span className="text-destructive" aria-hidden="true">*</span>
              </label>
              <input id="doc-file" ref={fileRef} type="file" required className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground" />
            </div>
          </div>
          <button type="submit" disabled={uploading} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
            登録
          </button>
        </form>

        {/* 検索3軸 */}
        <section aria-labelledby="search-heading" className="rounded-lg border p-4">
          <h2 id="search-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Search className="h-4 w-4" aria-hidden="true" /> 検索（3軸）
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div>
              <label htmlFor="s-date-from" className="mb-1 block text-xs font-medium">取引日（From）</label>
              <input id="s-date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="s-date-to" className="mb-1 block text-xs font-medium">取引日（To）</label>
              <input id="s-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="s-cp" className="mb-1 block text-xs font-medium">取引先</label>
              <input id="s-cp" type="text" value={searchCounterparty} onChange={(e) => setSearchCounterparty(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="s-amt-min" className="mb-1 block text-xs font-medium">金額（下限）</label>
              <input id="s-amt-min" type="number" value={amountMin} onChange={(e) => setAmountMin(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="s-amt-max" className="mb-1 block text-xs font-medium">金額（上限）</label>
              <input id="s-amt-max" type="number" value={amountMax} onChange={(e) => setAmountMax(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div className="flex items-end">
              <button type="button" onClick={handleSearch} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
                <Search className="h-4 w-4" aria-hidden="true" /> 検索
              </button>
            </div>
          </div>
        </section>

        {/* 検索結果 */}
        {loading ? (
          <SkeletonTable rows={5} columns={5} />
        ) : docs.length === 0 ? (
          <p className="text-sm text-muted-foreground">証憑がありません。検索条件を指定して検索してください。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">保存された証憑の検索結果</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">取引日</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">ファイル名</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">金額</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">取引先</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">ハッシュ(SHA-256)</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.archived_document_id} className="border-t">
                    <td className="px-3 py-2">{d.transaction_date}</td>
                    <td className="px-3 py-2">{d.file_name}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatYen(d.amount)}</td>
                    <td className="px-3 py-2">{d.counterparty_name || "-"}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground" title={d.file_hash}>
                        <ShieldCheck className="h-3 w-3 text-green-600" aria-hidden="true" />
                        {d.file_hash.slice(0, 12)}…
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
