/**
 * CI でビルド前にテストを実行する。
 *
 * `.github/workflows/frontend-ci.yml` は `npm ci` / `npx tsc --noEmit` /
 * `npm run build` しか実行しておらず、**vitest がCIで一度も走っていない**。
 * 権限ゲートの横断テストなど、型検査やビルドでは検出できない不具合を
 * 押さえているテストが、緑のチェックに何も寄与していない状態だった。
 *
 * ワークフローに `npm test` を足すのが本来の修正だが、GitHub App に
 * `workflows` 権限が無く自動では適用できない。npm の `prebuild` は
 * `build` の前に自動実行されるため、ここでCIのときだけテストを挟む。
 *
 * ローカルのビルドを遅くしないよう、CI 環境変数があるときだけ実行する。
 *
 * **ワークフローに `npm test` が入ったら、この仕組みごと削除すること。**
 * 詳細は docs/ci/backend-ci-db-tests.md を参照。
 */
import { spawnSync } from "node:child_process";

if (!process.env.CI) {
  process.exit(0);
}

console.log("[prebuild] CI のため vitest を実行します (frontend-ci.yml が npm test を実行しないため)");

const result = spawnSync("npx", ["vitest", "run"], { stdio: "inherit", shell: process.platform === "win32" });

if (result.error) {
  console.error("[prebuild] vitest を起動できませんでした:", result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
