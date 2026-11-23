"use client";

import { Fragment, useState, useEffect, useRef } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiPostMultipart } from "@/lib/api";
import { BANK_COLUMN_FIELDS, buildColumnMap } from "@/lib/bank-import";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Landmark, RefreshCw, Link2Off, Loader2, CheckCircle2, Sparkles } from "lucide-react";

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

interface ImportSkippedRow {
  row_number: number;
  reason: string;
}

interface ImportResult {
  imported: number;
  lines: BankStatementLine[];
  skipped: ImportSkippedRow[];
}

interface AccountItem {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  is_active: boolean;
}

interface CounterpartCandidate {
  account_id: string;
  account_code: string;
  account_name: string;
  confidence: number;
  support: number;
  exact_matches: number;
  reliable: boolean;
  matches_bank_account: boolean;
}

interface SuggestionResult {
  status: string;
  trained_examples: number;
  direction: string;
  candidates: CounterpartCandidate[];
}

interface PanelState {
  loading: boolean;
  creating: boolean;
  status: string;
  trainedExamples: number;
  candidates: CounterpartCandidate[];
  selectedAccountId: string;
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
  const canCreate = user?.permissions.includes("journal:create") ?? false;

  const [lines, setLines] = useState<BankStatementLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState<"all" | "unreconciled" | "reconciled">("all");

  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [columnInputs, setColumnInputs] = useState<Record<string, string>>({});
  const [skippedRows, setSkippedRows] = useState<ImportSkippedRow[]>([]);

  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [bankAccountId, setBankAccountId] = useState("");
  const [tolerance, setTolerance] = useState("3");
  const [reconciling, setReconciling] = useState(false);

  const [panels, setPanels] = useState<Record<string, PanelState>>({});

  const fetchLines = async () => {
    if (!companyId || !canView) return;
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
  }, [companyId, filter, canView]);

  useEffect(() => {
    if (!companyId || !canView) return;
    apiGet<AccountItem[]>("/masters", { company_id: companyId })
      .then((data) => setAccounts(data.filter((a) => a.is_active)))
      .catch(() => setAccounts([]));
  }, [companyId, canView]);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !companyId) return;
    setImporting(true);
    setError("");
    setNotice("");
    setSkippedRows([]);
    try {
      const form = new FormData();
      form.append("file", file);
      const columnMap = buildColumnMap(columnInputs);
      if (columnMap) {
        form.append("column_map", JSON.stringify(columnMap));
      }
      const result = await apiPostMultipart<ImportResult>(
        "/bank/import-statement",
        { company_id: companyId },
        form
      );
      setSkippedRows(result.skipped ?? []);
      setNotice(
        `${result.imported}件の明細を取り込みました。` +
          (result.skipped && result.skipped.length > 0
            ? ` ${result.skipped.length}件は読み飛ばしました（下に理由を表示しています）。`
            : "")
      );
      await fetchLines();
    } catch (err) {
      setError(err instanceof Error ? err.message : "取り込みに失敗しました");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const openPanel = async (line: BankStatementLine) => {
    if (!companyId) return;
    if (!bankAccountId) {
      setError("先に「銀行の勘定科目」を選んでください。");
      return;
    }
    setError("");
    setPanels((prev) => ({
      ...prev,
      [line.bank_statement_line_id]: {
        loading: true, creating: false, status: "", trainedExamples: 0, candidates: [], selectedAccountId: "",
      },
    }));
    try {
      const result = await apiGet<SuggestionResult>(
        `/bank/statement-lines/${line.bank_statement_line_id}/suggestion`,
        { company_id: companyId, bank_account_id: bankAccountId }
      );
      const preferred =
        result.candidates.find((c) => c.reliable) ?? result.candidates[0];
      setPanels((prev) => ({
        ...prev,
        [line.bank_statement_line_id]: {
          loading: false,
          creating: false,
          status: result.status,
          trainedExamples: result.trained_examples,
          candidates: result.candidates,
          selectedAccountId: preferred ? preferred.account_id : "",
        },
      }));
    } catch (err) {
      setPanels((prev) => {
        const next = { ...prev };
        delete next[line.bank_statement_line_id];
        return next;
      });
      setError(err instanceof Error ? err.message : "仕訳候補の取得に失敗しました");
    }
  };

  const closePanel = (lineId: string) => {
    setPanels((prev) => {
      const next = { ...prev };
      delete next[lineId];
      return next;
    });
  };

  const handleCreateJournal = async (line: BankStatementLine) => {
    if (!companyId || !bankAccountId) return;
    const panel = panels[line.bank_statement_line_id];
    if (!panel || !panel.selectedAccountId) return;
    setPanels((prev) => ({ ...prev, [line.bank_statement_line_id]: { ...panel, creating: true } }));
    setError("");
    try {
      await apiPost(
        `/bank/statement-lines/${line.bank_statement_line_id}/create-journal?company_id=${encodeURIComponent(companyId)}`,
        { bank_account_id: bankAccountId, counterpart_account_id: panel.selectedAccountId }
      );
      setNotice("仕訳ドラフトを作成しました。仕訳一覧で内容を確認し、確定すると次回から学習されます。");
      closePanel(line.bank_statement_line_id);
      await fetchLines();
    } catch (err) {
      setError(err instanceof Error ? err.message : "仕訳の作成に失敗しました");
      setPanels((prev) => ({
        ...prev,
        [line.bank_statement_line_id]: { ...panel, creating: false },
      }));
    }
  };

  const renderPanel = (line: BankStatementLine) => {
    const panel = panels[line.bank_statement_line_id];
    if (!panel) return null;
    if (panel.loading) {
      return (
        <p className="flex items-center gap-1 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> 過去の仕訳から候補を探しています...
        </p>
      );
    }
    const counterpartLabel = line.direction === "deposit" ? "貸方（相手科目）" : "借方（相手科目）";
    return (
      <div className="space-y-3">
        <p className="text-xs font-medium">
          {line.direction === "deposit" ? "入金" : "出金"} {formatYen(line.amount)} の仕訳化
          <span className="ml-2 font-normal text-muted-foreground">
            銀行科目は選択中の科目、相手科目を決めてドラフトを作ります。
          </span>
        </p>
        {panel.status === "insufficient_data" && (
          <p className="text-xs text-muted-foreground">
            過去の確定仕訳がまだ少ない（{panel.trainedExamples}件）ため、候補を出せません。
            科目を選んで仕訳化すると、その内容が次回から学習されます。
          </p>
        )}
        {panel.status === "no_matching_history" && (
          <p className="text-xs text-muted-foreground">
            過去の仕訳に似た取引が見つかりませんでした。科目を選んでください。
          </p>
        )}
        {panel.status === "ok" && panel.candidates.length === 0 && (
          <p className="text-xs text-muted-foreground">
            相手科目が1つに定まる候補がありませんでした。科目を選んでください。
          </p>
        )}
        {panel.candidates.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium">学習した候補</p>
            {panel.candidates.map((candidate) => (
              <label
                key={candidate.account_id}
                className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-xs"
              >
                <input
                  type="radio"
                  name={`counterpart-${line.bank_statement_line_id}`}
                  checked={panel.selectedAccountId === candidate.account_id}
                  onChange={() =>
                    setPanels((prev) => ({
                      ...prev,
                      [line.bank_statement_line_id]: { ...panel, selectedAccountId: candidate.account_id },
                    }))
                  }
                />
                <span>
                  {candidate.account_code} {candidate.account_name}
                </span>
                <span className="text-muted-foreground">
                  信頼度 {Math.round(candidate.confidence * 100)}% / 過去{candidate.support}件
                </span>
                {candidate.reliable && (
                  <span className="rounded-full bg-green-100 px-2 py-0.5 text-green-700">推奨</span>
                )}
              </label>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor={`counterpart-select-${line.bank_statement_line_id}`} className="mb-1 block text-xs font-medium">
              {counterpartLabel}
            </label>
            <select
              id={`counterpart-select-${line.bank_statement_line_id}`}
              value={panel.selectedAccountId}
              onChange={(e) =>
                setPanels((prev) => ({
                  ...prev,
                  [line.bank_statement_line_id]: { ...panel, selectedAccountId: e.target.value },
                }))
              }
              className="rounded-md border px-2 py-1.5 text-sm"
            >
              <option value="">選択してください</option>
              {accounts.map((account) => (
                <option key={account.account_id} value={account.account_id}>
                  {account.account_code} {account.account_name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => handleCreateJournal(line)}
            disabled={!panel.selectedAccountId || panel.creating}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
          >
            {panel.creating && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
            この内容で仕訳ドラフトを作成
          </button>
          <button
            type="button"
            onClick={() => closePanel(line.bank_statement_line_id)}
            className="rounded-md border px-3 py-1.5 text-sm"
          >
            閉じる
          </button>
        </div>
      </div>
    );
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
          <p className="text-sm">銀行明細CSVを取り込み、仕訳化（学習した候補つき）や既存仕訳への自動消込をします。</p>
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
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                列の対応付け（銀行ごとに列名が違う場合）
              </summary>
              <p className="mt-2 text-xs text-muted-foreground">
                空欄のままなら自動で判定します。うまく取り込めない列だけ、ファイルの列名をそのまま入力してください。
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {BANK_COLUMN_FIELDS.map((field) => (
                  <div key={field.key}>
                    <label htmlFor={`col-${field.key}`} className="mb-1 block text-xs font-medium">
                      {field.label}
                    </label>
                    <input
                      id={`col-${field.key}`}
                      type="text"
                      value={columnInputs[field.key] ?? ""}
                      onChange={(e) =>
                        setColumnInputs((prev) => ({ ...prev, [field.key]: e.target.value }))
                      }
                      placeholder={field.placeholder}
                      className="w-full rounded-md border px-2 py-1.5 text-sm"
                    />
                  </div>
                ))}
              </div>
            </details>
            {skippedRows.length > 0 && (
              <div className="mt-3 rounded-md border border-amber-500/40 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <p className="font-medium">読み飛ばした行（{skippedRows.length}件）</p>
                <ul className="mt-1 list-disc pl-4">
                  {skippedRows.map((row) => (
                    <li key={row.row_number}>
                      {row.row_number}行目: {row.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section aria-labelledby="reconcile-heading" className="rounded-lg border p-4">
            <h2 id="reconcile-heading" className="mb-3 text-sm font-semibold">自動消込</h2>
            <div className="space-y-3">
              <div>
                <label htmlFor="bank-account-id" className="mb-1 block text-xs font-medium">
                  銀行の勘定科目 <span className="text-destructive" aria-hidden="true">*</span>
                </label>
                <select
                  id="bank-account-id"
                  value={bankAccountId}
                  onChange={(e) => setBankAccountId(e.target.value)}
                  className="w-full rounded-md border px-3 py-2 text-sm"
                >
                  <option value="">選択してください</option>
                  {accounts.map((account) => (
                    <option key={account.account_id} value={account.account_id}>
                      {account.account_code} {account.account_name}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-muted-foreground">自動消込と仕訳化の両方で使います。</p>
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
                  <Fragment key={line.bank_statement_line_id}>
                  <tr className="border-t">
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
                      {!line.is_reconciled && canCreate && (
                        <button
                          type="button"
                          onClick={() =>
                            panels[line.bank_statement_line_id]
                              ? closePanel(line.bank_statement_line_id)
                              : openPanel(line)
                          }
                          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
                          aria-expanded={Boolean(panels[line.bank_statement_line_id])}
                          aria-label={`${line.transaction_date} ${formatYen(line.amount)} を仕訳化`}
                        >
                          <Sparkles className="h-3 w-3" aria-hidden="true" /> 仕訳化
                        </button>
                      )}
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
                  {panels[line.bank_statement_line_id] && (
                    <tr className="border-t bg-muted/30">
                      <td colSpan={6} className="px-3 py-3">
                        {renderPanel(line)}
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
