import { apiPost } from "./api";

/**
 * 自動仕訳学習の候補（POST /ai/suggest-journal）の画面側ロジック。
 *
 * バックエンド `services/journal_learning.py` が自社の確定済み仕訳だけから
 * 学んだ候補を返す。外部 LLM は使わない。このモジュールは、その応答を
 * 画面表示と仕訳入力フォームへの反映に変換する純粋な部分を受け持つ。
 *
 * 正直さの原則（バックエンド側の「控えめさの設計」と対にする）:
 * - 候補が無いときは理由（学習不足／前例なし）を必ず表示する。黙って空にしない。
 * - `reliable` でない候補は「根拠が弱い」ことを明示して控えめに扱う。
 * - 候補の反映は科目と合計金額まで。複数科目への金額配分は学習結果に
 *   含まれないので、画面側で勝手に割り振らず人の入力に残す。
 * - 反映しても自動で保存はしない。確定は人が行う。
 */

export interface SuggestionAccount {
  account_id: string;
  account_code: string;
  account_name: string;
}

export interface JournalSuggestionCandidate {
  debit_accounts: SuggestionAccount[];
  credit_accounts: SuggestionAccount[];
  /** 0..1。全候補のスコアに対する割合。 */
  confidence: number;
  /** この候補に寄与した過去仕訳の件数。 */
  support: number;
  /** 摘要が完全一致した件数。 */
  exact_matches: number;
  /** 自動入力に使ってよい水準か。false の候補は必ず人の確認が要る。 */
  reliable: boolean;
  /** 一致した単語特徴（根拠の一部）。 */
  matched_features: string[];
}

export type JournalSuggestionStatus = "ok" | "insufficient_data" | "no_matching_history";

export interface JournalSuggestionResponse {
  status: JournalSuggestionStatus;
  trained_examples: number;
  candidates: JournalSuggestionCandidate[];
}

/** バックエンドの JournalPatternLearner.MIN_EXAMPLES と同じ値。 */
export const MIN_LEARNING_EXAMPLES = 5;

export async function fetchJournalSuggestions(input: {
  companyId: string;
  description: string;
  amount: number;
}): Promise<JournalSuggestionResponse> {
  return apiPost<JournalSuggestionResponse>("/ai/suggest-journal", {
    description: input.description,
    amount: input.amount > 0 ? input.amount : 0,
    company_id: input.companyId,
  });
}

/**
 * 候補が無い理由の表示文。`ok` のときは null（候補一覧を表示する）。
 * 理由を返さず空表示にすることはしない。
 */
export function suggestionEmptyMessage(response: JournalSuggestionResponse): string | null {
  switch (response.status) {
    case "insufficient_data":
      return `学習データが不足しています。確定済みの仕訳が ${response.trained_examples} 件しかないため、候補を出せません（最低 ${MIN_LEARNING_EXAMPLES} 件の確定仕訳が必要です）。仕訳を確定していくうちに候補が出るようになります。`;
    case "no_matching_history":
      return `過去の確定仕訳（${response.trained_examples} 件）の中に、この摘要に似た取引が見つかりませんでした。候補は出せません。`;
    default:
      return null;
  }
}

/** 候補の根拠を人が読める形に組み立てる。 */
export function candidateEvidence(candidate: JournalSuggestionCandidate): string {
  const parts: string[] = [`過去の類似仕訳 ${candidate.support} 件`];
  if (candidate.exact_matches > 0) {
    parts.push(`摘要が完全一致 ${candidate.exact_matches} 件`);
  }
  if (candidate.matched_features.length > 0) {
    parts.push(`一致した語: ${candidate.matched_features.join("、")}`);
  }
  return parts.join(" / ");
}

export function confidencePercent(candidate: JournalSuggestionCandidate): number {
  return Math.round(candidate.confidence * 100);
}

/** 仕訳入力フォームの明細行（journals/new の JournalLine と同形）。 */
export interface JournalFormLine {
  debit_credit: "debit" | "credit";
  account_code: string;
  account_name: string;
  account_id: string;
  amount: string;
  tax_amount: string;
  description: string;
}

/**
 * 候補をフォームの明細行に変換する。
 *
 * 金額は借方・貸方それぞれ先頭行に合計を置き、残りの行は空欄にする。
 * 学習結果は科目の組み合わせだけを持ち、科目ごとの金額配分は含まない
 * ため、配分を推測で作らない。人が残りを入力して初めて貸借が合う。
 */
export function candidateToFormLines(
  candidate: JournalSuggestionCandidate,
  totalAmount: number,
): JournalFormLine[] {
  const amountText = totalAmount > 0 ? String(totalAmount) : "";
  const toLines = (
    accounts: SuggestionAccount[],
    side: "debit" | "credit",
  ): JournalFormLine[] =>
    accounts.map((account, index) => ({
      debit_credit: side,
      account_id: account.account_id,
      account_code: account.account_code,
      account_name: account.account_name,
      amount: index === 0 ? amountText : "",
      tax_amount: "0",
      description: "",
    }));
  return [
    ...toLines(candidate.debit_accounts, "debit"),
    ...toLines(candidate.credit_accounts, "credit"),
  ];
}
