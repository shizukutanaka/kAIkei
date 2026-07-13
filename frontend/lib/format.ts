/** 金額・日付などの表示フォーマット共通ヘルパー。 */

/** 金額を日本円表記（¥1,234,567）にする。null/不正値は "-" またはそのまま返す。 */
export function formatYen(amount: string | number | null | undefined): string {
  if (amount === null || amount === undefined || amount === "") return "-";
  const n = typeof amount === "number" ? amount : Number(amount);
  return Number.isNaN(n) ? String(amount) : `¥${n.toLocaleString("ja-JP")}`;
}
