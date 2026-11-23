import JournalDetail from "./journal-detail";

// 個人用単体パッケージの静的書き出し（output: "export"）では動的ルートに
// generateStaticParams が必須で、かつ "use client" と同じファイルに置けない。
// そのため本体（クライアントコンポーネント）は journal-detail.tsx に分け、
// ここはサーバ側の薄いラッパとする。
//
// 空配列では Next 14.2 が「未定義」とみなして書き出しが失敗するため、
// プレースホルダ "_" を1件だけ返す。実データのIDは UUID 形式で "_" とは
// 衝突しない。書き出し側では /journals/_ の画面部品一式が生成され、単体
// パッケージの静的配信（app/standalone.py）が実際のIDのURLへそれを返す。
// standalone 実行時は dynamicParams の既定（true）により従来どおり
// 任意のIDが動的描画されるため、挙動は変わらない。
export function generateStaticParams() {
  return [{ id: "_" }];
}

export default function JournalDetailPage() {
  return <JournalDetail />;
}
