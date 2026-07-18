"use client";

import { useState, useEffect, useRef } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiPostMultipart } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Landmark, Upload, RefreshCw, Link2Off, Loader2, CheckCircle2 } from "lucide-react";

interface BankStatementLine {
  bank_statement_line_id: string;
  transaction_date: string;
  direction: string;
  amount: string;
  balance: string | null;
  description: string | null;
  counterparty_name: string | null;
  is_reconciled: boolean;
  reconciled_journal_line_id: string | null;
  reconciled_at: string | null;
  source: string;
}

interface ImportResult {
  imported: number;
  lines: BankStatementLine[];
}

interface AutoReconcileResult {
  total_unreconciled: number;
  matched: number;
  unmatched: number;
}

const DIRECTION_LABELS: Record<string, string> = {
  deposit: "入金",
  withdrawal: "出金",
};

function formatYen(amount: string | null): string {
  if (amount === null) return "-";
  const n = Number(amount);
  if (Number.isNaN(n)) return amount;
  return `¥${n.toLocaleString("ja-JP")}`;
}

export default function BankReconciliationPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const canView = user?.permissions.includes("journal:read") ?? false;
  const canImport = user?.permissions.includes("integration:import") ?? false;
  const canReconcile = user?.permissions.includes("journal:update") ?? false;

  const [lines, setLines] = useState<BankStatementLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState<"all" | "unreconciled" | "reconciled">("all");

  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [bankAccountId, setBankAccountId] = useState("");
  const [tolerance, setTolerance] = useState("3");
  const [reconciling, setReconciling] = useState(false);

  const fetchLines = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId, limit: "200" };
      if (filter === "unreconciled") params.reconciled = "false";
      if (filter === "reconciled") params.reconciled = "true";
      const data = await apiGet<BankStatementLine[]>("/bank/statement-lines", params);
      setLines(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId && canView) fetchLines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, filter]);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !companyId) return;
    setImporting(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await apiPostMultipart<ImportResult>(
        "/bank/import-statement",
        { company_id: companyId },
        form
      );
      setNotice(`${result.imported}件の明細を取り込みました。`);
      await fetchLines();
    } catch (err) {
      setError(err instanceof Error ? err.message : "取り込みに失敗しました");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleAutoReconcile = async () => {
    if (!companyId || !bankAccountId) return;
    setReconciling(true);
    setError("");
    setNotice("");
    try {
      const result = await apiPost<AutoReconcileResult>(
        `/bank/auto-reconcile?company_id=${encodeURIComponent(companyId)}`,
        {
          bank_account_id: bankAccountId,
          date_tolerance_days: Number(tolerance) || 3,
          min_score: 0.6,
        }
      );
      setNotice(
        `自動消込を実行しました: ${result.matched}件を消込 / 未消込${result.unmatched}件（対象${result.total_unreconciled}件）。`
      );
      await fetchLines();
    } catch (err) {
      setError(err instanceof Error ? err.message : "自動消込に失敗しました");
    } finally {
      setReconciling(false);
    }
  };

  const handleUnmatch = async (lineId: string) => {
    if (!companyId) return;
    setError("");
    try {
      await apiPost<BankStatementLine>(
        `/bank/statement-lines/${lineId}/unmatch?company_id=${encodeURIComponent(companyId)}`,
        {}
      );
      await fetchLines();
    } catch (err) {
      setError(err instanceof Error ? err.message : "消込解除に失敗しました");
    }
  };

  if (!canView) {
    return (
      <PageLayout title="銀行明細・自動消込">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="銀行明細・自動消込">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Landmark className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">銀行明細CSVを取り込み、未消込の仕訳明細と自動で消込します。</p>
        </div>

        {error && (
          <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            {notice}
          </div>
        )}

        {/* 取込・自動消込操作 */}
        <div className="grid gap-4 md:grid-cols-2">
          <section aria-labelledby="import-heading" className="rounded-lg border p-4">
            <h2 id="import-heading" className="mb-3 text-sm font-semibold">明細CSV取込</h2>
            <label htmlFor="bank-csv" className="sr-only">銀行明細CSVファイル</label>
            <input
              id="bank-csv"
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={handleImport}
              disabled={!canImport || importing}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground disabled:opacity-50"
            />
            {!canImport && <p className="mt-2 text-xs text-muted-foreground">取込には integration:import 権限が必要です。</p>}
            {importing && (
              <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> 取り込み中...
              </p>
            )}
          </section>

          <section aria-labelledby="reconcile-heading" className="rounded-lg border p-4">
            <h2 id="reconcile-heading" className="mb-3 text-sm font-semibold">自動消込</h2>
            <div className="space-y-3">
              <div>
                <label htmlFor="bank-account-id" className="mb-1 block text-xs font-medium">
                  銀行勘定の勘定科目ID <span className="text-destructive" aria-hidden="true">*</span>
                </label>
                <input
                  id="bank-account-id"
                  type="text"
                  value={bankAccountId}
                  onChange={(e) => setBankAccountId(e.target.value)}
                  placeholder="勘定科目のUUID"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label htmlFor="tolerance" className="mb-1 block text-xs font-medium">日付許容日数</label>
                <input
                  id="tolerance"
                  type="number"
                  min={0}
                  max={31}
                  value={tolerance}
                  onChange={(e) => setTolerance(e.target.value)}
                  className="w-28 rounded-md border px-3 py-2 text-sm"
                />
              </div>
              <button
                type="button"
                onClick={handleAutoReconcile}
                disabled={!canReconcile || reconciling || !bankAccountId}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {reconciling ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
                自動消込を実行
              </button>
              {!canReconcile && <p className="text-xs text-muted-foreground">消込には journal:update 権限が必要です。</p>}
            </div>
          </section>
        </div>

        {/* フィルタ */}
        <div className="flex items-center gap-2">
          <label htmlFor="status-filter" className="text-sm font-medium">表示:</label>
          <select
            id="status-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value as typeof filter)}
            className="rounded-md border px-3 py-1.5 text-sm"
          >
            <option value="all">すべて</option>
            <option value="unreconciled">未消込のみ</option>
            <option value="reconciled">消込済みのみ</option>
          </select>
          <button
            type="button"
            onClick={fetchLines}
            className="ml-auto inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm"
            aria-label="一覧を再読み込み"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" /> 更新
          </button>
        </div>

        {/* 明細一覧 */}
        {loading ? (
          <SkeletonTable rows={6} columns={6} />
        ) : lines.length === 0 ? (
          <p className="text-sm text-muted-foreground">明細がありません。CSVを取り込んでください。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">銀行明細の一覧と消込状態</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">取引日</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">区分</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">金額</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">摘要 / 振込人</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">消込状態</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.bank_statement_line_id} className="border-t">
                    <td className="px-3 py-2">{line.transaction_date}</td>
                    <td className="px-3 py-2">
                      <span className={line.direction === "deposit" ? "text-green-700" : "text-red-700"}>
                        {DIRECTION_LABELS[line.direction] ?? line.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatYen(line.amount)}</td>
                    <td className="px-3 py-2">
                      <div>{line.description || "-"}</div>
                      {line.counterparty_name && (
                        <div className="text-xs text-muted-foreground">{line.counterparty_name}</div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {line.is_reconciled ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> 消込済
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">未消込</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {line.is_reconciled && canReconcile && (
                        <button
                          type="button"
                          onClick={() => handleUnmatch(line.bank_statement_line_id)}
                          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                          aria-label={`${line.transaction_date} ${formatYen(line.amount)} の消込を解除`}
                        >
                          <Link2Off className="h-3 w-3" aria-hidden="true" /> 解除
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
