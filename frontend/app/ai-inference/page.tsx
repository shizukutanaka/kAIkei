"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import PageLayout from "@/components/page-layout";
import { apiPost, apiPostMultipart } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { Upload, FileText, Sparkles, AlertCircle, ArrowRight, Loader2 } from "lucide-react";
import { SkeletonCard } from "@/components/skeleton";

interface InferenceResult {
  status: string;
  provider: string;
  results: Array<{
    account_code: string;
    account_name: string;
    debit_credit: string;
    amount: number;
    tax_rate: number;
    tax_type: string;
    confidence: number;
    reasoning: string;
  }>;
  debit_total: number;
  credit_total: number;
  is_balanced: boolean;
  avg_confidence: number;
  needs_human_review: boolean;
  context_used?: {
    similar_journals_count: number;
    patterns_count: number;
    combos_count: number;
  };
  pdf_extraction?: {
    file_name: string;
    extracted_amounts: number[];
    extracted_dates: string[];
    extracted_tax_rates: number[];
    potential_partner_names: string[];
    text_length: number;
    text_preview: string;
  };
}

export default function AiInferencePage() {
  const { companyId } = useCompany();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [transactionDate, setTransactionDate] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InferenceResult | null>(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      if (!description) {
        setDescription(selected.name.replace(/\.pdf$/i, ""));
      }
    }
  };

  const handleInfer = async () => {
    if (!companyId || !transactionDate) {
      setError("会社IDと取引日は必須です");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      if (file) {
        const formData = new FormData();
        formData.append("file", file);
        const data = await apiPostMultipart<InferenceResult>("/ai/infer-from-pdf", {
          company_id: companyId,
          transaction_date: transactionDate,
          amount: amount || "0",
          description,
        }, formData);
        setResult(data);
      } else {
        const data = await apiPost<InferenceResult>("/ai/infer-journal-enhanced", {
          description,
          amount: parseFloat(amount) || 0,
          transaction_date: transactionDate,
          company_id: companyId,
        });
        setResult(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
        <div className="mb-6 flex items-center gap-3">
          <Sparkles className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">AI仕訳推論</h1>
        </div>

        {!companyId && (
          <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
            サイドバーで会社を選択してください。
          </div>
        )}

        <div className="mb-6 rounded-lg border bg-card p-6">
          <h2 className="mb-4 text-lg font-semibold">入力</h2>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium">取引日</label>
            <input
              type="date"
              value={transactionDate}
              onChange={(e) => setTransactionDate(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          </div>

          <div className="mb-4 grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">摘要</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="取引の説明"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">金額（任意・PDFから自動抽出）</label>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0"
                className="w-full rounded-md border px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium">PDFファイル（任意）</label>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer items-center gap-3 rounded-md border-2 border-dashed p-4 hover:bg-accent"
            >
              <Upload className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {file ? file.name : "PDFをアップロード（請求書・領収書等）"}
              </span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>

          <button
            onClick={handleInfer}
            disabled={loading || !companyId || !transactionDate}
            className="flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {loading ? "推論中..." : "AI推論実行"}
          </button>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}

        {loading && (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {result && (
          <div className="space-y-4">
            <div className="rounded-lg border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold">推論結果</h2>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">
                    プロバイダ: {result.provider}
                  </span>
                  <span
                    className={`rounded px-2 py-1 text-xs font-medium ${
                      result.status === "auto_approved"
                        ? "bg-green-100 text-green-700"
                        : result.status === "needs_review"
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {result.status === "auto_approved"
                      ? "自動承認"
                      : result.status === "needs_review"
                      ? "要レビュー"
                      : result.status}
                  </span>
                </div>
              </div>

                <div className="mb-4 grid grid-cols-4 gap-4">
                <div className="rounded-md bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">平均信頼度</p>
                  <p className="text-lg font-bold">
                    {(result.avg_confidence * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="rounded-md bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">借方合計</p>
                  <p className="text-lg font-bold">¥{result.debit_total.toLocaleString()}</p>
                </div>
                <div className="rounded-md bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">貸方合計</p>
                  <p className="text-lg font-bold">¥{result.credit_total.toLocaleString()}</p>
                </div>
                <div className="rounded-md bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">貸借バランス</p>
                  <p className={`text-lg font-bold ${result.is_balanced ? "text-green-600" : "text-red-600"}`}>
                    {result.is_balanced ? "一致" : "不一致"}
                  </p>
                </div>
              </div>

              {result.context_used && (
                <div className="mb-4 rounded-md bg-blue-50 p-3 text-sm">
                  <p className="font-medium text-blue-700">過去仕訳コンテキスト</p>
                  <p className="text-blue-600">
                    類似仕訳: {result.context_used.similar_journals_count}件 / 
                    科目パターン: {result.context_used.patterns_count}件 / 
                    科目組み合わせ: {result.context_used.combos_count}件
                  </p>
                </div>
              )}

              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="p-2 text-left text-sm">借貸</th>
                    <th className="p-2 text-left text-sm">科目コード</th>
                    <th className="p-2 text-left text-sm">科目名</th>
                    <th className="p-2 text-right text-sm">金額</th>
                    <th className="p-2 text-right text-sm">税率</th>
                    <th className="p-2 text-right text-sm">信頼度</th>
                    <th className="p-2 text-left text-sm">推論理由</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((r, i) => (
                    <tr key={i} className="border-b">
                      <td className="p-2 text-sm">
                        {r.debit_credit === "debit" ? "借方" : "貸方"}
                      </td>
                      <td className="p-2 text-sm font-mono">{r.account_code}</td>
                      <td className="p-2 text-sm">{r.account_name}</td>
                      <td className="p-2 text-right text-sm">
                        ¥{r.amount.toLocaleString()}
                      </td>
                      <td className="p-2 text-right text-sm">
                        {(r.tax_rate * 100).toFixed(0)}%
                      </td>
                      <td className="p-2 text-right text-sm">
                        <span
                          className={
                            r.confidence >= 0.7
                              ? "text-green-600"
                              : r.confidence >= 0.5
                              ? "text-yellow-600"
                              : "text-red-600"
                          }
                        >
                          {(r.confidence * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="p-2 text-xs text-muted-foreground">
                        {r.reasoning}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => {
                    const lines = result.results.map((r) => ({
                      debit_credit: r.debit_credit,
                      account_code: r.account_code,
                      account_name: r.account_name,
                      account_id: "",
                      amount: String(r.amount),
                      tax_amount: String(Math.round(r.amount * r.tax_rate)),
                      description: r.reasoning,
                    }));
                    sessionStorage.setItem("ai_inference_lines", JSON.stringify(lines));
                    sessionStorage.setItem("ai_inference_summary", description);
                    sessionStorage.setItem("ai_inference_date", transactionDate);
                    router.push("/journals/new");
                  }}
                  className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  この内容で仕訳入力へ
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>

            {result.pdf_extraction && (
              <div className="rounded-lg border bg-card p-6">
                <div className="mb-3 flex items-center gap-2">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <h2 className="text-lg font-semibold">PDF抽出結果</h2>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">ファイル名</p>
                    <p className="font-medium">{result.pdf_extraction.file_name}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">テキスト長</p>
                    <p className="font-medium">{result.pdf_extraction.text_length}文字</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">抽出金額</p>
                    <p className="font-medium">
                      {result.pdf_extraction.extracted_amounts.map((a) => `¥${a.toLocaleString()}`).join(", ")}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">抽出日付</p>
                    <p className="font-medium">
                      {result.pdf_extraction.extracted_dates.join(", ")}
                    </p>
                  </div>
                  {result.pdf_extraction.potential_partner_names.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">推定取引先</p>
                      <p className="font-medium">
                        {result.pdf_extraction.potential_partner_names.join(", ")}
                      </p>
                    </div>
                  )}
                </div>
                {result.pdf_extraction.text_preview && (
                  <div className="mt-4">
                    <p className="mb-1 text-sm text-muted-foreground">テキストプレビュー</p>
                    <pre className="max-h-40 overflow-auto rounded-md bg-muted/30 p-3 text-xs">
                      {result.pdf_extraction.text_preview}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
    </PageLayout>
  );
}
