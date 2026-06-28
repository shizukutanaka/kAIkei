"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { BookOpen, Plus, Search } from "lucide-react";

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
  const canCreate = user?.permissions.includes("master:create") ?? false;
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
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

    try {
      await apiPost("/masters", { company_id: companyId, ...newAccount });
      setShowAddForm(false);
      setNewAccount({ account_code: "", account_name: "", account_type: "asset", debit_credit: "debit" });
      toast("科目を追加しました", "success");
      await fetchAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "科目の追加に失敗しました");
      toast(err instanceof Error ? err.message : "科目の追加に失敗しました", "error");
    }
  };

  const filtered = accounts.filter(
    (a) =>
      a.account_code.includes(search) ||
      a.account_name.includes(search)
  );

  return (
    <PageLayout>
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BookOpen className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">マスタ管理</h1>
          </div>
          {canCreate && (
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="h-4 w-4" />
              科目追加
            </button>
          )}
        </div>

        {showAddForm && (
          <div className="mb-6 rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">新規勘定科目</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium">科目コード</label>
                <input
                  type="text"
                  value={newAccount.account_code}
                  onChange={(e) => setNewAccount({ ...newAccount, account_code: e.target.value })}
                  placeholder="1000"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">科目名</label>
                <input
                  type="text"
                  value={newAccount.account_name}
                  onChange={(e) => setNewAccount({ ...newAccount, account_name: e.target.value })}
                  placeholder="現金"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">科目区分</label>
                <select
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
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              >
                追加
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

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="mb-4 flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="科目コード・科目名で検索"
            className="flex-1 rounded-md border px-3 py-2 text-sm"
          />
        </div>

        {loading ? (
          <p className="text-muted-foreground">読み込み中...</p>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">科目コード</th>
                  <th className="px-4 py-3 text-left font-medium">科目名</th>
                  <th className="px-4 py-3 text-left font-medium">区分</th>
                  <th className="px-4 py-3 text-left font-medium">借方/貸方</th>
                  <th className="px-4 py-3 text-left font-medium">状態</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((account) => (
                  <tr key={account.account_id} className="border-t">
                    <td className="px-4 py-3 font-mono">{account.account_code}</td>
                    <td className="px-4 py-3">{account.account_name}</td>
                    <td className="px-4 py-3">{ACCOUNT_TYPES[account.account_type] || account.account_type}</td>
                    <td className="px-4 py-3">{account.debit_credit === "debit" ? "借方" : "貸方"}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2 py-0.5 text-xs ${account.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                        {account.is_active ? "有効" : "無効"}
                      </span>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      勘定科目がありません
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
