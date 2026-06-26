"use client";

import { useState } from "react";
import Sidebar from "@/components/sidebar";

interface JournalLine {
  debit_credit: "debit" | "credit";
  account_code: string;
  account_name: string;
  amount: string;
  tax_amount: string;
  description: string;
}

export default function JournalEntryPage() {
  const [transactionDate, setTransactionDate] = useState("");
  const [summary, setSummary] = useState("");
  const [lines, setLines] = useState<JournalLine[]>([
    { debit_credit: "debit", account_code: "", account_name: "", amount: "", tax_amount: "0", description: "" },
    { debit_credit: "credit", account_code: "", account_name: "", amount: "", tax_amount: "0", description: "" },
  ]);

  const debitTotal = lines
    .filter((l) => l.debit_credit === "debit")
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const creditTotal = lines
    .filter((l) => l.debit_credit === "credit")
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const isBalanced = debitTotal === creditTotal && debitTotal > 0;

  const addLine = () => {
    setLines([...lines, { debit_credit: "debit", account_code: "", account_name: "", amount: "", tax_amount: "0", description: "" }]);
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

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <h1 className="mb-6 text-2xl font-bold">仕訳入力</h1>

        <div className="mb-4 flex gap-4">
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
          className="mb-4 rounded-md border px-4 py-2 text-sm hover:bg-accent"
        >
          + 行追加
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
            disabled={!isBalanced}
            className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            保存
          </button>
          <button
            disabled={!isBalanced}
            className="rounded-md border px-6 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            確定
          </button>
        </div>
      </main>
    </div>
  );
}
