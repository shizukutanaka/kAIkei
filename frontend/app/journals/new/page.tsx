"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { Save, Send, Plus, FilePlus, BookOpen, Loader2 } from "lucide-react";

interface Account {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_credit: string;
}

interface JournalLine {
  debit_credit: "debit" | "credit";
  account_code: string;
  account_name: string;
  account_id: string;
  amount: string;
  tax_amount: string;
  description: string;
}

export default function JournalEntryPage() {
  const { companyId } = useCompany();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const router = useRouter();
  const [transactionDate, setTransactionDate] = useState("");
  const [summary, setSummary] = useState("");
  const [lines, setLines] = useState<JournalLine[]>([
    { debit_credit: "debit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" },
    { debit_credit: "credit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" },
  ]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!companyId) {
      setAccounts([]);
      return;
    }
    setAccountsLoading(true);
    apiGet<Account[]>("/masters", { company_id: companyId })
      .then((data) => setAccounts(data || []))
      .catch(() => setAccounts([]))
      .finally(() => setAccountsLoading(false));
  }, [companyId]);

  useEffect(() => {
    const savedLines = sessionStorage.getItem("ai_inference_lines");
    const savedSummary = sessionStorage.getItem("ai_inference_summary");
    const savedDate = sessionStorage.getItem("ai_inference_date");
    if (savedLines) {
      try {
        const parsed = JSON.parse(savedLines) as JournalLine[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setLines(parsed);
        }
      } catch {
        // ignore
      }
      sessionStorage.removeItem("ai_inference_lines");
    }
    if (savedSummary) {
      setSummary(savedSummary);
      sessionStorage.removeItem("ai_inference_summary");
    }
    if (savedDate) {
      setTransactionDate(savedDate);
      sessionStorage.removeItem("ai_inference_date");
    }
  }, []);

  const debitTotal = lines
    .filter((l) => l.debit_credit === "debit")
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const creditTotal = lines
    .filter((l) => l.debit_credit === "credit")
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const isBalanced = debitTotal === creditTotal && debitTotal > 0;

  const addLine = () => {
    setLines([...lines, { debit_credit: "debit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" }]);
  };

  const selectAccount = (index: number, accountId: string) => {
    const account = accounts.find((a) => a.account_id === accountId);
    if (!account) return;
    const updated = [...lines];
    updated[index] = {
      ...updated[index],
      account_id: account.account_id,
      account_code: account.account_code,
      account_name: account.account_name,
    };
    setLines(updated);
  };

  const updateLine = (index: number, field: keyof JournalLine, value: string) => {
    const updated = [...lines];
    updated[index] = { ...updated[index], [field]: value };
    setLines(updated);
  };

  const removeLine = (index: number) => {
    if (lines.length > 2) {
      setLines(lines.filter((_, i) => i !== index));
    }
  };

  const handleSave = async () => {
    if (!isBalanced || !companyId || !transactionDate) return;
    setSaving(true);
    setError("");
    setResult(null);

    try {
      const payload = {
        company_id: companyId,
        transaction_date: transactionDate,
        voucher_type: "transfer",
        summary: summary || undefined,
        lines: lines.map((l) => ({
          debit_credit: l.debit_credit,
          account_id: l.account_id || l.account_code,
          amount: parseFloat(l.amount) || 0,
          tax_amount: parseFloat(l.tax_amount) || 0,
          description: l.description || undefined,
        })),
      };
      const data = await apiPost<Record<string, unknown>>("/journals", payload);
      setResult(data);
      toast("仕訳を保存しました", "success");
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
      toast(err instanceof Error ? err.message : "仕訳の保存に失敗しました", "error");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitForApproval = async () => {
    if (!isBalanced || !companyId || !transactionDate) return;
    const ok = await confirm({
      title: "承認待ちに提出",
      message: "この仕訳を承認待ちに提出しますか？提出後は編集できません。",
      confirmText: "提出",
      variant: "default",
    });
    if (!ok) return;
    const saved = await handleSave();
    if (!saved) return;
    const journalId = saved.journal_header_id as string;
    try {
      await apiPost(`/approvals/submit`, { journal_header_id: journalId });
      toast("仕訳を承認待ちに提出しました", "success");
      resetForm();
      router.push("/journals");
    } catch (err) {
      toast(err instanceof Error ? err.message : "提出に失敗しました", "error");
    }
  };

  const resetForm = () => {
    setTransactionDate("");
    setSummary("");
    setLines([
      { debit_credit: "debit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" },
      { debit_credit: "credit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" },
    ]);
    setResult(null);
    setError("");
  };

  return (
    <PageLayout title="仕訳入力">
      <div className="mb-6 flex items-center gap-3">
        <BookOpen className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">仕訳入力</h1>
      </div>

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

        {result && (
          <div role="status" className="mb-4 rounded-md border border-green-500/50 bg-green-50 p-4 text-sm text-green-700">
            仕訳を保存しました: {result.journal_number as string} (ID: {result.journal_header_id as string})
          </div>
        )}

        <div className="mb-4 flex gap-4">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-medium">科目マスタ</label>
            <div className="text-sm text-muted-foreground">
              {accountsLoading ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  読み込み中...
                </span>
              ) : accounts.length > 0 ? `${accounts.length}件の科目` : "会社を選択して科目を読み込み"}
            </div>
          </div>
          <div className="flex-1">
            <label htmlFor="journal_date" className="mb-1 block text-sm font-medium">取引日 <span className="text-destructive" aria-hidden="true">*</span></label>
            <input
              id="journal_date"
              type="date"
              value={transactionDate}
              onChange={(e) => setTransactionDate(e.target.value)}
              required
              aria-required="true"
              className="w-full rounded-md border px-3 py-2"
            />
          </div>
          <div className="flex-[2]">
            <label htmlFor="journal_summary" className="mb-1 block text-sm font-medium">摘要</label>
            <input
              id="journal_summary"
              type="text"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              maxLength={200}
              className="w-full rounded-md border px-3 py-2"
            />
          </div>
        </div>

        <div className="mb-4 overflow-x-auto">
        <table className="w-full border-collapse">
          <caption className="sr-only">仕訳入力明細</caption>
          <thead>
            <tr className="border-b bg-muted/50">
              <th scope="col" className="p-2 text-left text-sm">行</th>
              <th scope="col" className="p-2 text-left text-sm">借貸</th>
              <th scope="col" className="p-2 text-left text-sm">科目</th>
              <th scope="col" className="p-2 text-left text-sm">科目コード</th>
              <th scope="col" className="p-2 text-left text-sm">科目名</th>
              <th scope="col" className="p-2 text-right text-sm">金額</th>
              <th scope="col" className="p-2 text-right text-sm">消費税</th>
              <th scope="col" className="p-2 text-left text-sm">摘要</th>
              <th scope="col" className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className="border-b">
                <td className="p-2 text-sm">{i + 1}</td>
                <td className="p-2">
                  <select
                    value={line.debit_credit}
                    onChange={(e) => updateLine(i, "debit_credit", e.target.value)}
                    className="rounded border px-2 py-1 text-sm"
                  >
                    <option value="debit">借方</option>
                    <option value="credit">貸方</option>
                  </select>
                </td>
                <td className="p-2">
                  <select
                    value={line.account_id}
                    onChange={(e) => selectAccount(i, e.target.value)}
                    className="w-48 rounded border px-2 py-1 text-sm"
                  >
                    <option value="">科目を選択</option>
                    {accounts.map((a) => (
                      <option key={a.account_id} value={a.account_id}>
                        {a.account_code} - {a.account_name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="p-2">
                  <input
                    type="text"
                    value={line.account_code}
                    onChange={(e) => updateLine(i, "account_code", e.target.value)}
                    className="w-24 rounded border px-2 py-1 text-sm"
                    readOnly={!!line.account_id}
                  />
                </td>
                <td className="p-2">
                  <input
                    type="text"
                    value={line.account_name}
                    onChange={(e) => updateLine(i, "account_name", e.target.value)}
                    className="w-32 rounded border px-2 py-1 text-sm"
                    readOnly={!!line.account_id}
                  />
                </td>
                <td className="p-2">
                  <input
                    type="number"
                    value={line.amount}
                    onChange={(e) => updateLine(i, "amount", e.target.value)}
                    className="w-32 rounded border px-2 py-1 text-right text-sm"
                  />
                </td>
                <td className="p-2">
                  <input
                    type="number"
                    value={line.tax_amount}
                    onChange={(e) => updateLine(i, "tax_amount", e.target.value)}
                    className="w-24 rounded border px-2 py-1 text-right text-sm"
                  />
                </td>
                <td className="p-2">
                  <input
                    type="text"
                    value={line.description}
                    onChange={(e) => updateLine(i, "description", e.target.value)}
                    className="w-40 rounded border px-2 py-1 text-sm"
                  />
                </td>
                <td className="p-2">
                  {lines.length > 2 && (
                    <button
                      onClick={() => removeLine(i)}
                      className="text-sm text-destructive hover:underline"
                    >
                      削除
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>

        <button
          onClick={addLine}
          className="mb-4 flex items-center gap-1 rounded-md border px-4 py-2 text-sm hover:bg-accent"
        >
          <Plus className="h-4 w-4" />
          行追加
        </button>

        <div className="flex items-center gap-8 rounded-lg border bg-muted/30 p-4">
          <div>
            <span className="text-sm text-muted-foreground">借方合計: </span>
            <span className="font-bold">¥{debitTotal.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-sm text-muted-foreground">貸方合計: </span>
            <span className="font-bold">¥{creditTotal.toLocaleString()}</span>
          </div>
          <div>
            {isBalanced ? (
              <span className="text-sm font-medium text-green-600">✓ 貸借一致</span>
            ) : (
              <span className="text-sm font-medium text-destructive">
                ⚠ 貸借不一致 (差額: ¥{(debitTotal - creditTotal).toLocaleString()})
              </span>
            )}
          </div>
        </div>

        <div className="mt-6 flex gap-4">
          <button
            onClick={handleSave}
            disabled={!isBalanced || saving || !companyId}
            className="flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? "保存中..." : "保存"}
          </button>
          <button
            onClick={handleSubmitForApproval}
            disabled={!isBalanced || saving || !companyId}
            className="flex items-center gap-2 rounded-md border px-6 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {saving ? "提出中..." : "保存して承認待ちに提出"}
          </button>
          {result && (
            <button
              onClick={resetForm}
              className="flex items-center gap-2 rounded-md border px-6 py-2 text-sm font-medium hover:bg-accent"
            >
              <FilePlus className="h-4 w-4" />
              新規作成
            </button>
          )}
        </div>
    </PageLayout>
  );
}
