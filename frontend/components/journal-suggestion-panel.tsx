"use client";

import { useState } from "react";
import { GraduationCap, Loader2, MousePointerClick, TriangleAlert } from "lucide-react";
import {
  candidateEvidence,
  confidencePercent,
  fetchJournalSuggestions,
  suggestionEmptyMessage,
  type JournalSuggestionCandidate,
  type JournalSuggestionResponse,
} from "@/lib/journal-suggestion";

interface JournalSuggestionPanelProps {
  companyId: string | null;
  /** 仕訳入力画面の摘要。候補取得の説明文として使う。 */
  description: string;
  /** 現在の借方合計。候補取得と反映時の金額の目安。 */
  amount: number;
  /** 候補の「反映」が押されたとき。保存はしない（呼び出し側がフォームへ入れるだけ）。 */
  onApply: (candidate: JournalSuggestionCandidate) => void;
}

/**
 * 自動仕訳学習の候補パネル。
 *
 * 摘要を入れてボタンを押すと、自社の確定済み仕訳から学んだ候補を表示する。
 * この API は呼び出しごとに履歴から学習し直す重い処理のため、キー入力の
 * たびに自動送信はせず、明示的なボタン操作でのみ取得する。
 *
 * 候補が無い場合は理由を表示し、根拠の弱い候補（reliable でないもの）は
 * 控えめな見た目と注意文で出す。反映はフォームへ入れるだけで、保存や
 * 確定は行わない。
 */
export default function JournalSuggestionPanel({
  companyId,
  description,
  amount,
  onApply,
}: JournalSuggestionPanelProps) {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<JournalSuggestionResponse | null>(null);
  const [error, setError] = useState("");

  const trimmed = description.trim();
  const canFetch = !!companyId && trimmed.length > 0 && !loading;

  const handleFetch = async () => {
    if (!companyId || trimmed.length === 0) return;
    setLoading(true);
    setError("");
    setResponse(null);
    try {
      const data = await fetchJournalSuggestions({
        companyId,
        description: trimmed,
        amount,
      });
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "候補の取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const emptyMessage = response ? suggestionEmptyMessage(response) : null;

  return (
    <div className="mb-4 rounded-lg border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-2 text-sm font-medium">
          <GraduationCap className="h-4 w-4 text-primary" />
          学習候補（過去の確定仕訳から）
        </span>
        <button
          type="button"
          onClick={handleFetch}
          disabled={!canFetch}
          className="flex items-center gap-2 rounded-md border px-4 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {loading ? "候補を探しています..." : "候補を表示"}
        </button>
        {!companyId && <span className="text-sm text-muted-foreground">会社を選択すると使えます</span>}
        {companyId && trimmed.length === 0 && (
          <span className="text-sm text-muted-foreground">摘要を入力すると候補を探せます</span>
        )}
      </div>

      {error && (
        <div role="alert" className="mt-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          候補を取得できませんでした: {error}
        </div>
      )}

      {emptyMessage && (
        <div role="status" className="mt-3 rounded-md border border-yellow-500/50 bg-yellow-50 p-3 text-sm text-yellow-700">
          {emptyMessage}
        </div>
      )}

      {response && response.status === "ok" && response.candidates.length > 0 && (
        <div className="mt-3 space-y-3">
          {response.candidates.map((candidate, i) => (
            <div
              key={i}
              className={`rounded-md border bg-card p-3 ${candidate.reliable ? "" : "opacity-80"}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="text-sm">
                  <div>
                    <span className="text-muted-foreground">借方: </span>
                    {candidate.debit_accounts.map((a) => `${a.account_code} ${a.account_name}`).join("、") || "（科目を解決できませんでした）"}
                  </div>
                  <div>
                    <span className="text-muted-foreground">貸方: </span>
                    {candidate.credit_accounts.map((a) => `${a.account_code} ${a.account_name}`).join("、") || "（科目を解決できませんでした）"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {candidate.reliable ? (
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                      根拠が強い候補（目安 {confidencePercent(candidate)}%）
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
                      <TriangleAlert className="h-3 w-3" />
                      根拠が弱い候補（目安 {confidencePercent(candidate)}%）
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => onApply(candidate)}
                    className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
                  >
                    <MousePointerClick className="h-4 w-4" />
                    この候補を反映
                  </button>
                </div>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">根拠: {candidateEvidence(candidate)}</div>
              {!candidate.reliable && (
                <div className="mt-1 text-xs text-yellow-700">
                  根拠が弱いため、科目が正しいか必ず確認してください。
                </div>
              )}
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            候補は自社の確定済み仕訳 {response.trained_examples} 件からの学習です。反映しても自動では保存されません。金額の配分と内容の確認は人が行ってください。
          </p>
        </div>
      )}
    </div>
  );
}
