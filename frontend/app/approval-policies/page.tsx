"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { GitBranch, Plus, Trash2, Search, Loader2, CheckCircle2 } from "lucide-react";

interface ApprovalPolicy {
  approval_policy_id: string;
  document_type: string;
  min_amount: string | null;
  max_amount: string | null;
  approver_role: string;
  step_order: number;
  is_active: boolean;
}

const DOC_TYPES = [
  { value: "journal", label: "仕訳" },
  { value: "expense", label: "経費" },
  { value: "invoice", label: "請求書" },
  { value: "payment", label: "支払" },
];
const ROLES = [
  { value: "approver", label: "承認者" },
  { value: "accountant", label: "経理担当" },
  { value: "admin", label: "管理者" },
];

function yen(v: string | null): string {
  if (v === null) return "-";
  const n = Number(v);
  return Number.isNaN(n) ? v : `¥${n.toLocaleString("ja-JP")}`;
}

export default function ApprovalPoliciesPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canRead = user?.permissions.includes("master:read") ?? false;
  const canCreate = user?.permissions.includes("master:create") ?? false;
  const canDelete = user?.permissions.includes("master:delete") ?? false;

  const [policies, setPolicies] = useState<ApprovalPolicy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [docType, setDocType] = useState("expense");
  const [role, setRole] = useState("approver");
  const [stepOrder, setStepOrder] = useState("1");
  const [minAmount, setMinAmount] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [creating, setCreating] = useState(false);

  const [resolveDocType, setResolveDocType] = useState("expense");
  const [resolveAmount, setResolveAmount] = useState("");
  const [resolvedSteps, setResolvedSteps] = useState<string[] | null>(null);

  const fetchPolicies = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<ApprovalPolicy[]>("/approval-policies", { company_id: companyId });
      setPolicies(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && canRead) fetchPolicies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyId) return;
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const body: Record<string, unknown> = {
        document_type: docType,
        approver_role: role,
        step_order: Number(stepOrder) || 1,
      };
      if (minAmount) body.min_amount = minAmount;
      if (maxAmount) body.max_amount = maxAmount;
      await apiPost<ApprovalPolicy>(`/approval-policies?company_id=${encodeURIComponent(companyId)}`, body);
      setNotice("承認ポリシーを作成しました。");
      setMinAmount(""); setMaxAmount("");
      await fetchPolicies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!companyId) return;
    setError("");
    try {
      await apiDelete(`/approval-policies/${id}?company_id=${encodeURIComponent(companyId)}`);
      await fetchPolicies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "削除に失敗しました");
    }
  };

  const handleResolve = async () => {
    if (!companyId || !resolveAmount) return;
    setError("");
    try {
      const data = await apiGet<{ required_steps: string[] }>("/approval-policies/resolve", {
        company_id: companyId,
        document_type: resolveDocType,
        amount: resolveAmount,
      });
      setResolvedSteps(data.required_steps);
    } catch (err) {
      setError(err instanceof Error ? err.message : "解決に失敗しました");
    }
  };

  const roleLabel = (v: string) => ROLES.find((r) => r.value === v)?.label ?? v;
  const docLabel = (v: string) => DOC_TYPES.find((d) => d.value === v)?.label ?? v;

  if (!canRead) {
    return (
      <PageLayout title="承認ポリシー">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="承認ポリシー">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <GitBranch className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">文書種別・金額範囲に応じた承認ステップ（承認ロールの順序）を定義します。</p>
        </div>

        {error && <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {canCreate && (
          <form onSubmit={handleCreate} aria-labelledby="policy-heading" className="rounded-lg border p-4">
            <h2 id="policy-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold"><Plus className="h-4 w-4" aria-hidden="true" /> ポリシーの追加</h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
              <div>
                <label htmlFor="p-doc" className="mb-1 block text-xs font-medium">文書種別</label>
                <select id="p-doc" value={docType} onChange={(e) => setDocType(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                  {DOC_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="p-role" className="mb-1 block text-xs font-medium">承認ロール</label>
                <select id="p-role" value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm">
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="p-step" className="mb-1 block text-xs font-medium">ステップ順</label>
                <input id="p-step" type="number" min={1} value={stepOrder} onChange={(e) => setStepOrder(e.target.value)} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-min" className="mb-1 block text-xs font-medium">金額下限</label>
                <input id="p-min" type="number" value={minAmount} onChange={(e) => setMinAmount(e.target.value)} placeholder="任意" className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="p-max" className="mb-1 block text-xs font-medium">金額上限</label>
                <input id="p-max" type="number" value={maxAmount} onChange={(e) => setMaxAmount(e.target.value)} placeholder="任意" className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
            </div>
            <button type="submit" disabled={creating} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {creating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} 追加
            </button>
          </form>
        )}

        {loading ? (
          <SkeletonTable rows={4} columns={5} />
        ) : policies.length === 0 ? (
          <p className="text-sm text-muted-foreground">承認ポリシーがありません。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">承認ポリシーの一覧</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">文書種別</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">ステップ</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">承認ロール</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">金額範囲</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((p) => (
                  <tr key={p.approval_policy_id} className="border-t">
                    <td className="px-3 py-2">{docLabel(p.document_type)}</td>
                    <td className="px-3 py-2 text-center">{p.step_order}</td>
                    <td className="px-3 py-2">{roleLabel(p.approver_role)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{yen(p.min_amount)} 〜 {yen(p.max_amount)}</td>
                    <td className="px-3 py-2 text-right">
                      {canDelete && (
                        <button type="button" onClick={() => handleDelete(p.approval_policy_id)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground" aria-label={`${docLabel(p.document_type)} ステップ${p.step_order} のポリシーを削除`}>
                          <Trash2 className="h-3 w-3" aria-hidden="true" /> 削除
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 承認ステップ解決 */}
        <section aria-labelledby="resolve-heading" className="rounded-lg border p-4">
          <h2 id="resolve-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold"><Search className="h-4 w-4" aria-hidden="true" /> 承認ステップの確認</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="rv-doc" className="mb-1 block text-xs font-medium">文書種別</label>
              <select id="rv-doc" value={resolveDocType} onChange={(e) => setResolveDocType(e.target.value)} className="rounded-md border px-3 py-2 text-sm">
                {DOC_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="rv-amount" className="mb-1 block text-xs font-medium">金額</label>
              <input id="rv-amount" type="number" value={resolveAmount} onChange={(e) => setResolveAmount(e.target.value)} className="w-40 rounded-md border px-3 py-2 text-sm" />
            </div>
            <button type="button" onClick={handleResolve} disabled={!resolveAmount} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              <Search className="h-4 w-4" aria-hidden="true" /> 確認
            </button>
          </div>
          {resolvedSteps !== null && (
            <div className="mt-3 text-sm" role="status">
              {resolvedSteps.length === 0 ? (
                <p className="text-muted-foreground">該当する承認ステップはありません。</p>
              ) : (
                <p className="flex items-center gap-2">
                  必要な承認:
                  {resolvedSteps.map((s, i) => (
                    <span key={i} className="inline-flex items-center gap-1">
                      {i > 0 && <span aria-hidden="true">→</span>}
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{roleLabel(s)}</span>
                    </span>
                  ))}
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </PageLayout>
  );
}
