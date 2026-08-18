"use client";

import { AlertTriangle } from "lucide-react";

/**
 * 「この数値は概算です」を利用者に見せる警告。
 *
 * 給与・賞与・消費税申告には、法定の算出方法をまだ実装できていない項目がある。
 * サーバは応答に `estimate_notice` を載せているが、画面が出さなければ利用者は
 * 概算だと分からないまま給与明細や申告書に使ってしまう。
 *
 * 通知が無い（= 法定計算に対応した）場合は何も描画しない。対応が済めば
 * 警告は自動的に消える。
 */
export function EstimateNotice({ notice }: { notice?: string | null }) {
  if (!notice) return null;

  return (
    <div
      role="note"
      className="mb-4 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{notice}</span>
    </div>
  );
}

export default EstimateNotice;
