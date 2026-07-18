"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { Calculator, Plus, TrendingDown, Trash2, RefreshCw, Loader2 } from "lucide-react";
import { SkeletonTable } from "@/components/skeleton";

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
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showForm, setShowForm] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
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

  const handleCreate = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const errors: Record<string, string> = {};
    if (!formData.asset_code) errors.asset_code = "資産コードは必須です";
    if (!formData.asset_name) errors.asset_name = "資産名は必須です";
    if (!formData.acquisition_date) errors.acquisition_date = "取得日は必須です";
    if (!formData.acquisition_cost) errors.acquisition_cost = "取得価額は必須です";
    if (!formData.useful_life_months) errors.useful_life_months = "耐用年数は必須です";
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast("必須項目を入力してください", "warning");
      return;
    }
    setFieldErrors({});
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
    setActionLoading(`dep-${assetId}`);
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
    } finally {
      setActionLoading(null);
    }
  };

  const handleDispose = async (assetId: string) => {
    if (!await confirm({ title: "資産除却", message: "この資産を除却しますか？", confirmText: "除却", variant: "danger" })) return;
    setActionLoading(`disp-${assetId}`);
    try {
      await apiDelete(`/fixed-assets/${assetId}?disposal_date=${new Date().toISOString().split("T")[0]}`);
      toast("資産を除却しました", "success");
      await fetchAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "除却に失敗しました");
      toast("除却に失敗しました", "error");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <PageLayout title="固定資産">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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

        <div className="mb-4 flex items-center justify-end">
          <button
            onClick={fetchAssets}
            disabled={loading || !companyId}
            className="flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "取得中..." : "更新"}
          </button>
        </div>

        {showForm && (
          <form onSubmit={handleCreate} className="mb-6 rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">新規資産登録</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="asset_code" className="mb-1 block text-sm font-medium">資産コード <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="asset_code" type="text" value={formData.asset_code} onChange={(e) => { setFormData({ ...formData, asset_code: e.target.value }); if (fieldErrors.asset_code) setFieldErrors({ ...fieldErrors, asset_code: "" }); }} required aria-required="true" aria-invalid={!!fieldErrors.asset_code} aria-describedby={fieldErrors.asset_code ? "asset_code-error" : undefined} className="w-full rounded-md border px-3 py-2 text-sm aria-[invalid=true]:border-destructive" />
                {fieldErrors.asset_code && <p id="asset_code-error" className="mt-1 text-xs text-destructive">{fieldErrors.asset_code}</p>}
              </div>
              <div>
                <label htmlFor="asset_name" className="mb-1 block text-sm font-medium">資産名 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="asset_name" type="text" value={formData.asset_name} onChange={(e) => { setFormData({ ...formData, asset_name: e.target.value }); if (fieldErrors.asset_name) setFieldErrors({ ...fieldErrors, asset_name: "" }); }} required aria-required="true" aria-invalid={!!fieldErrors.asset_name} aria-describedby={fieldErrors.asset_name ? "asset_name-error" : undefined} className="w-full rounded-md border px-3 py-2 text-sm aria-[invalid=true]:border-destructive" />
                {fieldErrors.asset_name && <p id="asset_name-error" className="mt-1 text-xs text-destructive">{fieldErrors.asset_name}</p>}
              </div>
              <div>
                <label htmlFor="asset_category" className="mb-1 block text-sm font-medium">カテゴリ</label>
                <select id="asset_category" value={formData.asset_category} onChange={(e) => setFormData({ ...formData, asset_category: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="acquisition_date" className="mb-1 block text-sm font-medium">取得日 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="acquisition_date" type="date" value={formData.acquisition_date} onChange={(e) => { setFormData({ ...formData, acquisition_date: e.target.value }); if (fieldErrors.acquisition_date) setFieldErrors({ ...fieldErrors, acquisition_date: "" }); }} required aria-required="true" aria-invalid={!!fieldErrors.acquisition_date} aria-describedby={fieldErrors.acquisition_date ? "acquisition_date-error" : undefined} className="w-full rounded-md border px-3 py-2 text-sm aria-[invalid=true]:border-destructive" />
                {fieldErrors.acquisition_date && <p id="acquisition_date-error" className="mt-1 text-xs text-destructive">{fieldErrors.acquisition_date}</p>}
              </div>
              <div>
                <label htmlFor="acquisition_cost" className="mb-1 block text-sm font-medium">取得価額 <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="acquisition_cost" type="number" inputMode="decimal" value={formData.acquisition_cost} onChange={(e) => { setFormData({ ...formData, acquisition_cost: e.target.value }); if (fieldErrors.acquisition_cost) setFieldErrors({ ...fieldErrors, acquisition_cost: "" }); }} required aria-required="true" aria-invalid={!!fieldErrors.acquisition_cost} aria-describedby={fieldErrors.acquisition_cost ? "acquisition_cost-error" : undefined} min="0" className="w-full rounded-md border px-3 py-2 text-sm aria-[invalid=true]:border-destructive" />
                {fieldErrors.acquisition_cost && <p id="acquisition_cost-error" className="mt-1 text-xs text-destructive">{fieldErrors.acquisition_cost}</p>}
              </div>
              <div>
                <label htmlFor="useful_life_months" className="mb-1 block text-sm font-medium">耐用年数（月） <span className="text-destructive" aria-hidden="true">*</span></label>
                <input id="useful_life_months" type="number" inputMode="numeric" value={formData.useful_life_months} onChange={(e) => { setFormData({ ...formData, useful_life_months: e.target.value }); if (fieldErrors.useful_life_months) setFieldErrors({ ...fieldErrors, useful_life_months: "" }); }} required aria-required="true" aria-invalid={!!fieldErrors.useful_life_months} aria-describedby={fieldErrors.useful_life_months ? "useful_life_months-error" : "useful_life_months-hint"} min="1" className="w-full rounded-md border px-3 py-2 text-sm aria-[invalid=true]:border-destructive" />
                {fieldErrors.useful_life_months ? <p id="useful_life_months-error" className="mt-1 text-xs text-destructive">{fieldErrors.useful_life_months}</p> : <p id="useful_life_months-hint" className="mt-1 text-xs text-muted-foreground">月数で入力してください（例: 60ヶ月=5年）</p>}
              </div>
              <div>
                <label htmlFor="depreciation_method" className="mb-1 block text-sm font-medium">償却方法</label>
                <select id="depreciation_method" value={formData.depreciation_method} onChange={(e) => setFormData({ ...formData, depreciation_method: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                  <option value="straight_line">定額法</option>
                </select>
              </div>
              <div>
                <label htmlFor="salvage_value" className="mb-1 block text-sm font-medium">残存価額</label>
                <input id="salvage_value" type="number" inputMode="decimal" value={formData.salvage_value} onChange={(e) => setFormData({ ...formData, salvage_value: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <button type="submit" disabled={loading} className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {loading ? "登録中..." : "登録"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="rounded-md border px-4 py-2 text-sm">
                キャンセル
              </button>
            </div>
          </form>
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

        {loading && <SkeletonTable rows={5} columns={8} />}

        {assets.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">固定資産一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left font-medium">資産コード</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">資産名</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">カテゴリ</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">取得価額</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">償却累計額</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">帳簿価額</th>
                  <th scope="col" className="px-4 py-3 text-center font-medium">ステータス</th>
                  <th scope="col" className="px-4 py-3 text-center font-medium">操作</th>
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
                          <button onClick={() => handleDepreciate(a.asset_id, a.asset_name)} disabled={actionLoading === `dep-${a.asset_id}`} className="flex items-center gap-1 rounded border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50" title="償却実行">
                            {actionLoading === `dep-${a.asset_id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <TrendingDown className="h-3 w-3" />}
                            償却
                          </button>
                          <button onClick={() => handleDispose(a.asset_id)} disabled={actionLoading === `disp-${a.asset_id}`} className="flex items-center gap-1 rounded border border-destructive/50 px-2 py-1 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-50" title="除却">
                            {actionLoading === `disp-${a.asset_id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                            除却
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 bg-muted/30 font-bold">
                  <td colSpan={3} className="px-4 py-3">合計</td>
                  <td className="px-4 py-3 text-right">¥{assets.reduce((s, a) => s + parseInt(a.acquisition_cost), 0).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">¥{assets.reduce((s, a) => s + parseInt(a.accumulated_depreciation), 0).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">¥{assets.reduce((s, a) => s + parseInt(a.net_book_value), 0).toLocaleString()}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        {assets.length === 0 && !loading && companyId && !error && (
          <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
            <Calculator className="mb-3 h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">資産データがありません。新規登録から登録してください。</p>
          </div>
        )}
    </PageLayout>
  );
}
