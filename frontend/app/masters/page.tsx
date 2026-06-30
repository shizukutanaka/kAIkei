"use client";

import { useState, useEffect, useDeferredValue, useMemo } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { SkeletonTable } from "@/components/skeleton";
import { BookOpen, Plus, Search, Download, Filter, RefreshCw, Loader2, X } from "lucide-react";

interface Account {
  account_id: string;
  company_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_credit: string;
  is_active: boolean;
}

const ACCOUNT_TYPES: Record<string, string> = {
  asset: "資産",
  liability: "負債",
  equity: "純資産",
  revenue: "収益",
  expense: "費用",
};

export default function MastersPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const canCreate = user?.permissions.includes("master:create") ?? false;
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [initLoading, setInitLoading] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [newAccount, setNewAccount] = useState({
    account_code: "",
    account_name: "",
    account_type: "asset",
    debit_credit: "debit",
  });

  useEffect(() => {
    fetchAccounts();
  }, [companyId]);

  const fetchAccounts = async () => {
    if (!companyId) {
      setLoading(false);
      setAccounts([]);
      return;
    }
    setLoading(true);
    try {
      const data = await apiGet<Account[]>("/masters", { company_id: companyId });
      setAccounts(data);
    } catch {
      setError("勘定科目の取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const handleAddAccount = async () => {
    if (!companyId || !newAccount.account_code || !newAccount.account_name) {
      setError("科目コードと科目名を入力してください");
      return;
    }

    setAddLoading(true);
    try {
      await apiPost("/masters", { company_id: companyId, ...newAccount });
      setShowAddForm(false);
      setNewAccount({ account_code: "", account_name: "", account_type: "asset", debit_credit: "debit" });
      toast("科目を追加しました", "success");
      await fetchAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "科目の追加に失敗しました");
      toast(err instanceof Error ? err.message : "科目の追加に失敗しました", "error");
    } finally {
      setAddLoading(false);
    }
  };

  const handleInitStandard = async () => {
    if (!companyId) return;
    const ok = await confirm({
      title: "標準科目セット初期化",
      message: "標準勘定科目セットを初期化します。既存の科目は重複しません。続行しますか？",
      confirmText: "初期化",
      variant: "default",
    });
    if (!ok) return;
    setInitLoading(true);
    try {
      const result = await apiPost<Account[]>(`/masters/initialize-standard-accounts?company_id=${companyId}`, {});
      toast(`標準科目セットを初期化しました（${result.length}件追加）`, "success");
      await fetchAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "初期化に失敗しました");
      toast(err instanceof Error ? err.message : "初期化に失敗しました", "error");
    } finally {
      setInitLoading(false);
    }
  };

  const handleToggleActive = async (account: Account) => {
    try {
      const updated = await apiPut<Account>(`/masters/${account.account_id}`, {
        is_active: !account.is_active,
      });
      setAccounts(accounts.map((a) => (a.account_id === account.account_id ? updated : a)));
      toast(`科目「${account.account_name}」を${!account.is_active ? "有効" : "無効"}にしました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "更新に失敗しました", "error");
    }
  };

  const deferredSearch = useDeferredValue(search);
  const deferredTypeFilter = useDeferredValue(typeFilter);

  const filtered = useMemo(() =>
    accounts.filter(
      (a) =>
        (a.account_code.includes(deferredSearch) ||
        a.account_name.includes(deferredSearch)) &&
        (!deferredTypeFilter || a.account_type === deferredTypeFilter)
    ),
    [accounts, deferredSearch, deferredTypeFilter]
  );

  return (
    <PageLayout>
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <BookOpen className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">マスタ管理</h1>
          </div>
          {canCreate && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleInitStandard}
                disabled={initLoading || !companyId}
                className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
              >
                {initLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {initLoading ? "初期化中..." : "標準科目セット"}
              </button>
              <button
                onClick={() => setShowAddForm(!showAddForm)}
                className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              >
                <Plus className="h-4 w-4" />
                科目追加
              </button>
            </div>
          )}
        </div>

        {showAddForm && (
          <div className="mb-6 rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">新規勘定科目</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="account_code" className="mb-1 block text-sm font-medium">科目コード</label>
                <input
                  id="account_code"
                  type="text"
                  value={newAccount.account_code}
                  onChange={(e) => setNewAccount({ ...newAccount, account_code: e.target.value })}
                  placeholder="1000"
                  required
                  aria-required="true"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label htmlFor="account_name" className="mb-1 block text-sm font-medium">科目名</label>
                <input
                  id="account_name"
                  type="text"
                  value={newAccount.account_name}
                  onChange={(e) => setNewAccount({ ...newAccount, account_name: e.target.value })}
                  placeholder="現金"
                  required
                  aria-required="true"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label htmlFor="account_type" className="mb-1 block text-sm font-medium">科目区分</label>
                <select
                  id="account_type"
                  value={newAccount.account_type}
                  onChange={(e) => setNewAccount({ ...newAccount, account_type: e.target.value })}
                  className="w-full rounded-md border px-3 py-2 text-sm"
                >
                  {Object.entries(ACCOUNT_TYPES).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">借方/貸方</label>
                <select
                  value={newAccount.debit_credit}
                  onChange={(e) => setNewAccount({ ...newAccount, debit_credit: e.target.value })}
                  className="w-full rounded-md border px-3 py-2 text-sm"
                >
                  <option value="debit">借方</option>
                  <option value="credit">貸方</option>
                </select>
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <button
                onClick={handleAddAccount}
                disabled={addLoading}
                className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {addLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {addLoading ? "追加中..." : "追加"}
              </button>
              <button
                onClick={() => setShowAddForm(false)}
                className="rounded-md border px-4 py-2 text-sm font-medium"
              >
                キャンセル
              </button>
            </div>
          </div>
        )}

        {!companyId && (
          <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
            サイドバーで会社を選択してください。
          </div>
        )}

        {error && (
          <div role="alert" className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="科目コード・科目名で検索"
                enterKeyHint="search"
                className="w-full rounded-md border px-3 py-2 pl-8 pr-7 text-sm"
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
              className="rounded-md border px-2 py-2 text-sm"
            >
              <option value="">全区分</option>
              {Object.entries(ACCOUNT_TYPES).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <span className="text-xs text-muted-foreground">{filtered.length} / {accounts.length} 件</span>
          <button
            onClick={() => fetchAccounts()}
            disabled={loading || !companyId}
            className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "取得中..." : "更新"}
          </button>
        </div>

        {loading ? (
          <SkeletonTable rows={6} columns={5} />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
            <caption className="sr-only">勘定科目一覧</caption>
            <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left font-medium">科目コード</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">科目名</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">区分</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">借方/貸方</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">状態</th>
                  {canCreate && <th scope="col" className="px-4 py-3 text-center font-medium">操作</th>}
                </tr>
              </thead>
              <tbody>
                {filtered.map((account) => (
                  <tr key={account.account_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3 font-mono">{account.account_code}</td>
                    <td className="px-4 py-3">{account.account_name}</td>
                    <td className="px-4 py-3">{ACCOUNT_TYPES[account.account_type] || account.account_type}</td>
                    <td className="px-4 py-3">{account.debit_credit === "debit" ? "借方" : "貸方"}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2 py-0.5 text-xs ${account.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                        {account.is_active ? "有効" : "無効"}
                      </span>
                    </td>
                    {canCreate && (
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => handleToggleActive(account)}
                          className={`rounded px-2 py-1 text-xs font-medium ${account.is_active ? "bg-gray-100 text-gray-600 hover:bg-gray-200" : "bg-green-100 text-green-700 hover:bg-green-200"}`}
                        >
                          {account.is_active ? "無効化" : "有効化"}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={canCreate ? 6 : 5} className="px-4 py-12">
                      <div className="flex flex-col items-center justify-center">
                        <BookOpen className="mb-3 h-10 w-10 text-muted-foreground" />
                        <p className="text-sm text-muted-foreground">
                          {companyId ? "勘定科目がありません。標準科目セットを初期化するか、科目を追加してください。" : "会社を選択してください。"}
                        </p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
    </PageLayout>
  );
}
