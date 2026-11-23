/**
 * 銀行明細CSV取り込みの列対応（column_map）の組み立て。
 *
 * 銀行・カード会社ごとにCSVの列名が違うため、取り込み画面で
 * 「どの列が何か」を利用者が指定できるようにする。指定はバックエンドの
 * canonical名（date/deposit/...）→ 実際のヘッダ名 の辞書として送る。
 */

export interface BankColumnField {
  key: string;
  label: string;
  placeholder: string;
}

export const BANK_COLUMN_FIELDS: BankColumnField[] = [
  { key: "date", label: "日付の列", placeholder: "例: 取引日" },
  { key: "deposit", label: "入金額の列", placeholder: "例: 入金額" },
  { key: "withdrawal", label: "出金額の列", placeholder: "例: 出金額" },
  { key: "amount", label: "金額の列（入出金が1列の場合）", placeholder: "例: ご利用金額" },
  { key: "direction", label: "入出金区分の列", placeholder: "例: 入出金区分" },
  { key: "balance", label: "残高の列", placeholder: "例: 残高" },
  { key: "description", label: "摘要の列", placeholder: "例: 摘要" },
  { key: "counterparty", label: "振込人名の列", placeholder: "例: 振込人名カナ" },
];

/**
 * 入力欄の値から column_map を作る。空欄は含めない。
 * 何も指定が無ければ null（＝サーバー側の自動判定に任せる）。
 */
export function buildColumnMap(inputs: Record<string, string>): Record<string, string> | null {
  const map: Record<string, string> = {};
  for (const field of BANK_COLUMN_FIELDS) {
    const value = (inputs[field.key] ?? "").trim();
    if (value) {
      map[field.key] = value;
    }
  }
  return Object.keys(map).length > 0 ? map : null;
}
