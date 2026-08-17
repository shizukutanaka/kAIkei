"use client";

import { useState, useEffect, useCallback } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { formatYen } from "@/lib/format";
import { Banknote, Plus, Check, Play, Ban, Loader2, CheckCircle2, X } from "lucide-react";

interface PaymentRequest {
  payment_request_id: string;
  company_id: string;
  payment_date: string;
  payment_amount: string;
  dest_bank_code: string | null;
  dest_branch_code: string | null;
  dest_account_type: string | null;
  dest_account_no: string | null;
  dest_account_name_kana: string | null;
  status: string;
}

const STATUS_LABELS: Record<string, string> = {
  draft: "下書き",
  approved: "承認済み",
  executed: "実行済み",
  cancelled: "取消",
};

const STATUS_FILTERS = [
  { value: "", label: "すべて" },
  { value: "draft", label: "下書き" },
  { value: "approved", label: "承認済み" },
  { value: "executed", label: "実行済み" },
  { value: "cancelled", label: "取消" },
];

export default function PaymentsPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("master:read") ?? false;
  const canCreate = user?.permissions.includes("master:create") ?? false;
  const canUpdate = user?.permissions.includes("master:update") ?? false;

  const [rows, setRows] = useState<PaymentRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    payment_date: "",
    payment_amount: "",
    dest_bank_code: "",
    dest_branch_code: "",
    dest_account_type: "ordinary",
    dest_account_no: "",
    dest_account_name_kana: "",
  });

  const load = useCallback(async () => {
    // 権限が無い場合は表示も抑止しているため、確実に403になるリクエストを送らない。
    if (!companyId || !canRead) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId };
      if (statusFilter) params.status = statusFilter;
      const data = await apiGet<PaymentRequest[]>("/payments", params);
      setRows(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "読み込みに失敗しました");
    } finally {
      setLoading(false);
    }
  }, [companyId, statusFilter, canRead]);

  useEffect(() => {
    load();
  }, [load]);

  const setField = (k: keyof typeof form, v: string) => setForm((prev) => ({ ...prev, [k]: v }));

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyId || !form.payment_date || !form.payment_amount) {
      setError("支払日と支払金額は必須です。");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiPost<PaymentRequest>("/payments", {
        company_id: companyId,
        payment_date: form.payment_date,
        payment_amount: form.payment_amount,
        dest_bank_code: form.dest_bank_code || null,
        dest_branch_code: form.dest_branch_code || null,
        dest_account_type: form.dest_account_type || null,
        dest_account_no: form.dest_account_no || null,
        dest_account_name_kana: form.dest_account_name_kana || null,
      });
      setNotice("支払申請（下書き）を作成しました。");
      setForm((prev) => ({ ...prev, payment_amount: "", dest_account_no: "", dest_account_name_kana: "" }));
      setShowCreate(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const transition = async (row: PaymentRequest, action: "approve" | "execute" | "cancel", label: string) => {
    if (!companyId) return;
    setBusy(true);
    setError("");
    try {
      await apiPost<PaymentRequest>(`/payments/${row.payment_request_id}/${action}?company_id=${encodeURIComponent(companyId)}`, {});
      setNotice(`支払申請を${label}しました。`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${label}に失敗しました`);
    } finally {
      setBusy(false);
    }
  };

  if (!canRead) {
    return (
      <PageLayout title="支払申請">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（master:read が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="支払申請">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Banknote className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">支払申請を作成し、承認（下書き→承認済み）・実行（承認済み→実行済み）で管理します。承認/実行済みが全銀エクスポートの対象です。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {canCreate && !showCreate && (
            <button type="button" onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
              <Plus className="h-4 w-4" aria-hidden="true" /> 支払申請を作成
            </button>
          )}
          <div className="flex items-center gap-2">
            <label htmlFor="status-filter" className="text-xs font-medium text-muted-foreground">状態</label>
            <select id="status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
              {STATUS_FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
        </div>

        {showCreate && canCreate && (
          <form onSubmit={handleCreate} aria-labelledby="pay-create-heading" className="rounded-lg border p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 id="pay-create-heading" className="text-sm font-semibold">支払申請の作成</h2>
              <button type="button" onClick={() => setShowCreate(false)} aria-label="フォームを閉じる" className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              <div>
                <label htmlFor="p-date" className="mb-1 block text-xs font-medium">支払日 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="p-date" type="date" required value={form.payment_date} onChange={(e) => setField("payment_date", e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-amount" className="mb-1 block text-xs font-medium">支払金額 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="p-amount" type="number" required min={0} step="1" value={form.payment_amount} onChange={(e) => setField("payment_amount", e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-kana" className="mb-1 block text-xs font-medium">振込先口座名義（カナ）</label>
                <input id="p-kana" type="text" value={form.dest_account_name_kana} onChange={(e) => setField("dest_account_name_kana", e.target.value)} placeholder="ﾃｽﾄﾀﾛｳ" className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-bank" className="mb-1 block text-xs font-medium">銀行コード</label>
                <input id="p-bank" type="text" maxLength={4} value={form.dest_bank_code} onChange={(e) => setField("dest_bank_code", e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-branch" className="mb-1 block text-xs font-medium">支店コード</label>
                <input id="p-branch" type="text" maxLength={3} value={form.dest_branch_code} onChange={(e) => setField("dest_branch_code", e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-type" className="mb-1 block text-xs font-medium">口座種別</label>
                <select id="p-type" value={form.dest_account_type} onChange={(e) => setField("dest_account_type", e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                  <option value="ordinary">普通</option>
                  <option value="checking">当座</option>
                </select>
              </div>
              <div>
                <label htmlFor="p-no" className="mb-1 block text-xs font-medium">口座番号</label>
                <input id="p-no" type="text" maxLength={7} value={form.dest_account_no} onChange={(e) => setField("dest_account_no", e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
            </div>
            <button type="submit" disabled={busy} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} 作成
            </button>
          </form>
        )}

        {loading ? (
          <SkeletonTable rows={5} columns={5} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">支払申請がありません。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">支払申請一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">支払日</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">金額</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">振込先</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">状態</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.payment_request_id} className="border-t">
                    <td className="px-3 py-2">{r.payment_date}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatYen(r.payment_amount)}</td>
                    <td className="px-3 py-2">
                      {r.dest_account_name_kana || "-"}
                      {r.dest_bank_code && <span className="ml-1 text-xs text-muted-foreground">{r.dest_bank_code}-{r.dest_branch_code}-{r.dest_account_no}</span>}
                    </td>
                    <td className="px-3 py-2">{STATUS_LABELS[r.status] ?? r.status}</td>
                    <td className="px-3 py-2 text-right">
                      {canUpdate && (
                        <div className="inline-flex gap-1">
                          {r.status === "draft" && (
                            <button type="button" onClick={() => transition(r, "approve", "承認")} disabled={busy} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:text-green-700 disabled:opacity-50">
                              <Check className="h-3 w-3" aria-hidden="true" /> 承認
                            </button>
                          )}
                          {r.status === "approved" && (
                            <button type="button" onClick={() => transition(r, "execute", "実行")} disabled={busy} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:text-foreground disabled:opacity-50">
                              <Play className="h-3 w-3" aria-hidden="true" /> 実行
                            </button>
                          )}
                          {(r.status === "draft" || r.status === "approved") && (
                            <button type="button" onClick={() => transition(r, "cancel", "取消")} disabled={busy} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-destructive disabled:opacity-50">
                              <Ban className="h-3 w-3" aria-hidden="true" /> 取消
                            </button>
                          )}
                        </div>
                      )}
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
