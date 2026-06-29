"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { Calculator, Plus, TrendingDown, Trash2, Search } from "lucide-react";

interface FixedAsset {
  asset_id: string;
  asset_code: string;
  asset_name: string;
  asset_category: string;
  acquisition_date: string;
  acquisition_cost: string;
  useful_life_months: number;
  depreciation_method: string;
  salvage_value: string;
  accumulated_depreciation: string;
  is_disposed: boolean;
  disposal_date: string | null;
  net_book_value: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  building: "建物",
  machinery: "機械装置",
  vehicle: "車両運搬具",
  furniture: "器具備品",
  software: "ソフトウェア",
  land: "土地",
};

export default function FixedAssetsPage() {
  const { companyId } = useCompany();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const [assets, setAssets] = useState<FixedAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    asset_code: "",
    asset_name: "",
    asset_category: "machinery",
    acquisition_date: new Date().toISOString().split("T")[0],
    acquisition_cost: "",
    useful_life_months: "60",
    depreciation_method: "straight_line",
    salvage_value: "0",
  });

  const fetchAssets = async () => {
    if (!companyId) {
      setError("サイドバーで会社IDを入力してください");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<FixedAsset[]>("/fixed-assets", { company_id: companyId });
      setAssets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) fetchAssets();
  }, [companyId]);

  const handleCreate = async () => {
    setLoading(true);
    setError("");
    try {
      await apiPost("/fixed-assets", {
        company_id: companyId,
        ...formData,
        acquisition_cost: parseFloat(formData.acquisition_cost),
        useful_life_months: parseInt(formData.useful_life_months),
        salvage_value: parseFloat(formData.salvage_value),
      });
      setShowForm(false);
      setFormData({
        asset_code: "",
        asset_name: "",
        asset_category: "machinery",
        acquisition_date: new Date().toISOString().split("T")[0],
        acquisition_cost: "",
        useful_life_months: "60",
        depreciation_method: "straight_line",
        salvage_value: "0",
      });
      toast("資産を登録しました", "success");
      await fetchAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
      toast("資産の登録に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDepreciate = async (assetId: string, assetName: string) => {
    const ok = await confirm({
      title: "償却実行",
      message: `資産「${assetName}」の償却を実行しますか？`,
      confirmText: "償却実行",
      variant: "default",
    });
    if (!ok) return;
    const now = new Date();
    try {
      await apiPost(`/fixed-assets/${assetId}/depreciate`, {
        fiscal_year: now.getFullYear(),
        month: now.getMonth() + 1,
      });
      toast("償却を実行しました", "success");
      await fetchAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "償却に失敗しました");
      toast("償却に失敗しました", "error");
    }
  };

  const handleDispose = async (assetId: string) => {
    if (!await confirm({ title: "資産除却", message: "この資産を除却しますか？", confirmText: "除却", variant: "danger" })) return;
    try {
      await apiDelete(`/fixed-assets/${assetId}?disposal_date=${new Date().toISOString().split("T")[0]}`);
      toast("資産を除却しました", "success");
      await fetchAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "除却に失敗しました");
      toast("除却に失敗しました", "error");
    }
  };

  return (
    <PageLayout>
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Calculator className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">固定資産</h1>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            <Plus className="h-4 w-4" />
            新規登録
          </button>
        </div>

        <div className="mb-4 flex items-center justify-between rounded-lg border bg-card p-4">
          <div>
            <p className="text-sm font-medium">会社ID</p>
            <p className="text-sm text-muted-foreground">{companyId || "未設定"}</p>
          </div>
          <button
            onClick={fetchAssets}
            disabled={loading || !companyId}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
            {loading ? "取得中..." : "更新"}
          </button>
        </div>

        {showForm && (
          <div className="mb-6 rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">新規資産登録</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium">資産コード</label>
                <input type="text" value={formData.asset_code} onChange={(e) => setFormData({ ...formData, asset_code: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">資産名</label>
                <input type="text" value={formData.asset_name} onChange={(e) => setFormData({ ...formData, asset_name: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">カテゴリ</label>
                <select value={formData.asset_category} onChange={(e) => setFormData({ ...formData, asset_category: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">取得日</label>
                <input type="date" value={formData.acquisition_date} onChange={(e) => setFormData({ ...formData, acquisition_date: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">取得価額</label>
                <input type="number" value={formData.acquisition_cost} onChange={(e) => setFormData({ ...formData, acquisition_cost: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">耐用年数（月）</label>
                <input type="number" value={formData.useful_life_months} onChange={(e) => setFormData({ ...formData, useful_life_months: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">償却方法</label>
                <select value={formData.depreciation_method} onChange={(e) => setFormData({ ...formData, depreciation_method: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                  <option value="straight_line">定額法</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">残存価額</label>
                <input type="number" value={formData.salvage_value} onChange={(e) => setFormData({ ...formData, salvage_value: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={handleCreate} disabled={loading} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                {loading ? "登録中..." : "登録"}
              </button>
              <button onClick={() => setShowForm(false)} className="rounded-md border px-4 py-2 text-sm">
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

        {assets.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">資産コード</th>
                  <th className="px-4 py-3 text-left font-medium">資産名</th>
                  <th className="px-4 py-3 text-left font-medium">カテゴリ</th>
                  <th className="px-4 py-3 text-right font-medium">取得価額</th>
                  <th className="px-4 py-3 text-right font-medium">償却累計額</th>
                  <th className="px-4 py-3 text-right font-medium">帳簿価額</th>
                  <th className="px-4 py-3 text-center font-medium">ステータス</th>
                  <th className="px-4 py-3 text-center font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((a) => (
                  <tr key={a.asset_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3 font-mono">{a.asset_code}</td>
                    <td className="px-4 py-3">{a.asset_name}</td>
                    <td className="px-4 py-3">{CATEGORY_LABELS[a.asset_category] || a.asset_category}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(a.acquisition_cost).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(a.accumulated_depreciation).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-medium">¥{parseInt(a.net_book_value).toLocaleString()}</td>
                    <td className="px-4 py-3 text-center">
                      {a.is_disposed ? (
                        <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">除却済</span>
                      ) : (
                        <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">稼働中</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {!a.is_disposed && (
                        <div className="flex items-center justify-center gap-2">
                          <button onClick={() => handleDepreciate(a.asset_id, a.asset_name)} className="flex items-center gap-1 rounded border px-2 py-1 text-xs hover:bg-accent" title="償却実行">
                            <TrendingDown className="h-3 w-3" />
                            償却
                          </button>
                          <button onClick={() => handleDispose(a.asset_id)} className="flex items-center gap-1 rounded border border-destructive/50 px-2 py-1 text-xs text-destructive hover:bg-destructive/10" title="除却">
                            <Trash2 className="h-3 w-3" />
                            除却
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {assets.length === 0 && !loading && companyId && !error && (
          <p className="text-center text-sm text-muted-foreground">資産データがありません</p>
        )}
    </PageLayout>
  );
}
