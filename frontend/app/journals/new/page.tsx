"use client";

import { useState } from "react";
import Sidebar from "@/components/sidebar";
import { Save, Send, Plus } from "lucide-react";

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
  const [companyId, setCompanyId] = useState("");
  const [transactionDate, setTransactionDate] = useState("");
  const [summary, setSummary] = useState("");
  const [lines, setLines] = useState<JournalLine[]>([
    { debit_credit: "debit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" },
    { debit_credit: "credit", account_code: "", account_name: "", account_id: "", amount: "", tax_amount: "0", description: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");

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

    const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";

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

      const response = await fetch("http://localhost:8000/api/v1/journals", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "保存に失敗しました");
      }
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <h1 className="mb-6 text-2xl font-bold">仕訳入力</h1>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {result && (
          <div className="mb-4 rounded-md border border-green-500/50 bg-green-50 p-4 text-sm text-green-700">
            仕訳を保存しました: {result.journal_number as string} (ID: {result.journal_header_id as string})
          </div>
        )}

        <div className="mb-4 flex gap-4">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-medium">会社ID</label>
            <input
              type="text"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              placeholder="UUID"
              className="w-full rounded-md border px-3 py-2"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-sm font-medium">取引日</label>
            <input
              type="date"
              value={transactionDate}
              onChange={(e) => setTransactionDate(e.target.value)}
              className="w-full rounded-md border px-3 py-2"
            />
          </div>
          <div className="flex-[2]">
            <label className="mb-1 block text-sm font-medium">摘要</label>
            <input
              type="text"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              maxLength={200}
              className="w-full rounded-md border px-3 py-2"
            />
          </div>
        </div>

        <table className="mb-4 w-full border-collapse">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="p-2 text-left text-sm">行</th>
              <th className="p-2 text-left text-sm">借貸</th>
              <th className="p-2 text-left text-sm">科目コード</th>
              <th className="p-2 text-left text-sm">科目名</th>
              <th className="p-2 text-right text-sm">金額</th>
              <th className="p-2 text-right text-sm">消費税</th>
              <th className="p-2 text-left text-sm">摘要</th>
              <th className="p-2"></th>
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
                  <input
                    type="text"
                    value={line.account_code}
                    onChange={(e) => updateLine(i, "account_code", e.target.value)}
                    className="w-24 rounded border px-2 py-1 text-sm"
                  />
                </td>
                <td className="p-2">
                  <input
                    type="text"
                    value={line.account_name}
                    onChange={(e) => updateLine(i, "account_name", e.target.value)}
                    className="w-32 rounded border px-2 py-1 text-sm"
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
            <Save className="h-4 w-4" />
            {saving ? "保存中..." : "保存"}
          </button>
          <button
            disabled={!isBalanced || saving || !companyId}
            className="flex items-center gap-2 rounded-md border px-6 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            確定
          </button>
        </div>
      </main>
    </div>
  );
}
