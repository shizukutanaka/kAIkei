/** @type {import('next').NextConfig} */
const nextConfig = {
  // 既定は従来どおり standalone（Docker 配布用）。
  // 個人用単体パッケージでは NEXT_OUTPUT=export で静的書き出しに切り替える
  // （バックエンドが同じオリジンで画面を配信するため。packaging/ 参照）。
  output: process.env.NEXT_OUTPUT || "standalone",
};

export default nextConfig;
