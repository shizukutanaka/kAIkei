"use client";

import { useState, useEffect, useDeferredValue, useMemo } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { SkeletonTable } from "@/components/skeleton";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import { Handshake, Plus, Search, Trash2, Pencil, X, Users, RefreshCw, Loader2 } from "lucide-react";
import { Pagination } from "@/components/pagination";

interface Partner {
  partner_id: string;
  company_id: string;
  partner_code: string;
  partner_name: string;
  partner_type: string;
  postal_code: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  contact_person: string | null;
  payment_terms: string | null;
  is_active: boolean;
}

const PARTNER_TYPE_LABELS: Record<string, string> = {
  customer: "顧客",
  supplier: "仕入先",
  both: "顧客・仕入先",
  other: "その他",
};

const emptyForm = {
  partner_code: "",
  partner_name: "",
  partner_type: "customer",
  postal_code: "",
  address: "",
  phone: "",
  email: "",
  contact_person: "",
  payment_terms: "",
};

export default function PartnersPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const perms = user?.permissions ?? [];
  const canCreate = perms.includes("master:create");
  const canUpdate = perms.includes("master:update");
  const canDelete = perms.includes("master:delete");

  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 50;
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState(emptyForm);

  const isDirty = showForm && (formData.partner_code !== emptyForm.partner_code || formData.partner_name !== emptyForm.partner_name);
  useUnsavedChanges(isDirty);

  const fetchPartners = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<{ items: Partner[]; total: number; page: number; page_size: number }>("/partners", { company_id: companyId, page: String(page), page_size: String(pageSize) });
      setPartners(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) fetchPartners();
  }, [companyId, page]);

  const deferredSearch = useDeferredValue(search);
  const deferredTypeFilter = useDeferredValue(typeFilter);

  const filtered = useMemo(() => partners.filter((p) => {
    const matchesSearch =
      !deferredSearch ||
      p.partner_code.toLowerCase().includes(deferredSearch.toLowerCase()) ||
      p.partner_name.toLowerCase().includes(deferredSearch.toLowerCase());
    const matchesType = !deferredTypeFilter || p.partner_type === deferredTypeFilter;
    return matchesSearch && matchesType;
  }), [partners, deferredSearch, deferredTypeFilter]);

  const handleSave = async () => {
    if (!formData.partner_code || !formData.partner_name) {
      toast("取引先コードと名称は必須です", "warning");
      return;
    }
    setLoading(true);
    try {
      const payload = {
        company_id: companyId,
        ...formData,
        postal_code: formData.postal_code || null,
        address: formData.address || null,
        phone: formData.phone || null,
        email: formData.email || null,
        contact_person: formData.contact_person || null,
        payment_terms: formData.payment_terms || null,
      };
      if (editingId) {
        await apiPut(`/partners/${editingId}?company_id=${companyId}`, payload);
        toast("取引先を更新しました", "success");
      } else {
        await apiPost("/partners", payload);
        toast("取引先を登録しました", "success");
      }
      setShowForm(false);
      setEditingId(null);
      setFormData(emptyForm);
      await fetchPartners();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "保存に失敗しました";
      setError(msg);
      toast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (p: Partner) => {
    setEditingId(p.partner_id);
    setFormData({
      partner_code: p.partner_code,
      partner_name: p.partner_name,
      partner_type: p.partner_type,
      postal_code: p.postal_code || "",
      address: p.address || "",
      phone: p.phone || "",
      email: p.email || "",
      contact_person: p.contact_person || "",
      payment_terms: p.payment_terms || "",
    });
    setShowForm(true);
  };

  const handleDelete = async (partnerId: string) => {
    if (!await confirm({ title: "取引先削除", message: "この取引先を削除しますか？", confirmText: "削除", variant: "danger" })) return;
    try {
      await apiDelete(`/partners/${partnerId}?company_id=${companyId}`);
      toast("取引先を削除しました", "success");
      await fetchPartners();
    } catch (err) {
      toast(err instanceof Error ? err.message : "削除に失敗しました", "error");
    }
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData(emptyForm);
  };

  return (
    <PageLayout>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Handshake className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">取引先マスタ</h1>
        </div>
        {canCreate && !showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            <Plus className="h-4 w-4" />
            取引先追加
          </button>
        )}
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {!companyId && (
        <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          サイドバーで会社を選択してください。
        </div>
      )}

      {showForm && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">{editingId ? "取引先編集" : "新規取引先登録"}</h2>
            <button onClick={handleCancel} className="rounded-md p-2 hover:bg-accent" aria-label="閉じる">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="partner_code" className="mb-1 block text-sm font-medium">取引先コード <span className="text-destructive" aria-hidden="true">*</span></label>
              <input
                id="partner_code"
                type="text"
                value={formData.partner_code}
                onChange={(e) => setFormData({ ...formData, partner_code: e.target.value })}
                disabled={!!editingId}
                required
                aria-required="true"
                className="w-full rounded-md border px-3 py-2 text-sm disabled:bg-muted"
              />
            </div>
            <div>
              <label htmlFor="partner_name" className="mb-1 block text-sm font-medium">取引先名 <span className="text-destructive" aria-hidden="true">*</span></label>
              <input
                id="partner_name"
                type="text"
                value={formData.partner_name}
                onChange={(e) => setFormData({ ...formData, partner_name: e.target.value })}
                required
                aria-required="true"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="partner_type" className="mb-1 block text-sm font-medium">取引先区分</label>
              <select
                id="partner_type"
                value={formData.partner_type}
                onChange={(e) => setFormData({ ...formData, partner_type: e.target.value })}
                className="w-full rounded-md border px-3 py-2 text-sm"
              >
                {Object.entries(PARTNER_TYPE_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="contact_person" className="mb-1 block text-sm font-medium">担当者</label>
              <input
                id="contact_person"
                type="text"
                value={formData.contact_person}
                onChange={(e) => setFormData({ ...formData, contact_person: e.target.value })}
                autoComplete="name"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="postal_code" className="mb-1 block text-sm font-medium">郵便番号</label>
              <input
                id="postal_code"
                type="text"
                inputMode="numeric"
                value={formData.postal_code}
                onChange={(e) => setFormData({ ...formData, postal_code: e.target.value })}
                autoComplete="postal-code"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="phone" className="mb-1 block text-sm font-medium">電話番号</label>
              <input
                id="phone"
                type="tel"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                autoComplete="tel"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium">メールアドレス</label>
              <input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                autoComplete="email"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="payment_terms" className="mb-1 block text-sm font-medium">支払条件</label>
              <input
                id="payment_terms"
                type="text"
                value={formData.payment_terms}
                onChange={(e) => setFormData({ ...formData, payment_terms: e.target.value })}
                placeholder="例: 月末締め翌月末払い"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div className="col-span-2">
              <label htmlFor="address" className="mb-1 block text-sm font-medium">住所</label>
              <input
                id="address"
                type="text"
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleSave}
              disabled={loading}
              className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {loading ? "保存中..." : editingId ? "更新" : "登録"}
            </button>
            <button onClick={handleCancel} className="rounded-md border px-4 py-2 text-sm">
              キャンセル
            </button>
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="コード・名称で検索"
            enterKeyHint="search"
            className="w-full rounded-md border py-1.5 pl-8 pr-7 text-sm"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label="クリア"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-accent"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-md border px-2 py-1.5 text-sm"
        >
          <option value="">全区分</option>
          {Object.entries(PARTNER_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground">{filtered.length}/{total}件</span>
        <button
          onClick={() => fetchPartners()}
          disabled={loading || !companyId}
          className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "取得中..." : "更新"}
        </button>
      </div>

      {loading && partners.length === 0 ? (
        <SkeletonTable rows={6} columns={7} />
      ) : filtered.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">取引先一覧</caption>
            <thead className="bg-muted/50">
              <tr>
                <th scope="col" className="px-4 py-3 text-left font-medium">コード</th>
                <th scope="col" className="px-4 py-3 text-left font-medium">名称</th>
                <th scope="col" className="px-4 py-3 text-left font-medium">区分</th>
                <th scope="col" className="px-4 py-3 text-left font-medium">担当者</th>
                <th scope="col" className="px-4 py-3 text-left font-medium">連絡先</th>
                <th scope="col" className="px-4 py-3 text-center font-medium">状態</th>
                <th scope="col" className="px-4 py-3 text-center font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.partner_id} className="border-t hover:bg-muted/30">
                  <td className="px-4 py-3 font-mono">{p.partner_code}</td>
                  <td className="px-4 py-3 font-medium">{p.partner_name}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded px-2 py-0.5 text-xs ${
                      p.partner_type === "customer" ? "bg-blue-100 text-blue-700" :
                      p.partner_type === "supplier" ? "bg-green-100 text-green-700" :
                      p.partner_type === "both" ? "bg-purple-100 text-purple-700" :
                      "bg-gray-100 text-gray-700"
                    }`}>
                      {PARTNER_TYPE_LABELS[p.partner_type] || p.partner_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">{p.contact_person || "-"}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {p.phone || p.email || "-"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded px-2 py-0.5 text-xs ${p.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                      {p.is_active ? "有効" : "無効"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      {canUpdate && (
                        <button
                          onClick={() => handleEdit(p)}
                          className="flex items-center gap-1 rounded border px-2 py-1 text-xs hover:bg-accent"
                          title="編集"
                        >
                          <Pencil className="h-3 w-3" />
                          編集
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(p.partner_id)}
                          className="flex items-center gap-1 rounded border border-destructive/50 px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
                          title="削除"
                        >
                          <Trash2 className="h-3 w-3" />
                          削除
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <Users className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "取引先データがありません。取引先追加から登録してください。" : "会社を選択してください。"}
          </p>
        </div>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
    </PageLayout>
  );
}
