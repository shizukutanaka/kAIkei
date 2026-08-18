import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";

/**
 * 権限ゲートの横断テスト。
 *
 * 各画面は権限が無いとき「権限がありません」と描画するが、それは描画時の判定に
 * すぎず、マウント時の useEffect が先にAPIを呼んでしまう不具合が複数の画面で
 * 発生していた。画面には何も出ないのに裏でリクエストが飛ぶ状態になる。
 *
 * 画面ごとにテストを増やすと同じ不具合がまた別の画面で再発するため、
 * 「権限ゼロで描画したらデータ取得APIを一切呼ばない」を横断的に固定する。
 * 新しい画面を追加したらこのリストにも追加すること。
 */

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPut = vi.fn();
const apiPatch = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  apiGet: (...a: unknown[]) => apiGet(...a),
  apiPost: (...a: unknown[]) => apiPost(...a),
  apiPut: (...a: unknown[]) => apiPut(...a),
  apiPatch: (...a: unknown[]) => apiPatch(...a),
  apiDelete: (...a: unknown[]) => apiDelete(...a),
}));
vi.mock("@/lib/company-context", () => ({ useCompany: () => ({ companyId: "company-1" }) }));
// 権限ゼロのユーザー。どの画面も何も取得してはいけない。
vi.mock("@/lib/use-user", () => ({ useUser: () => ({ user: { permissions: [] } }) }));
vi.mock("@/components/page-layout", () => ({
  default: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

import AiInferenceLogsPage from "./ai-inference-logs/page";
import ApprovalPoliciesPage from "./approval-policies/page";
import ArAgingPage from "./ar-aging/page";
import AuditPage from "./audit/page";
import AuditDetectionPage from "./audit-detection/page";
import BankPage from "./bank/page";
import BudgetsPage from "./budgets/page";
import JobsPage from "./jobs/page";
import OpsPage from "./ops/page";
import PaymentsPage from "./payments/page";
import TaxAdjustmentsPage from "./tax-adjustments/page";
import TreasuryPage from "./treasury/page";

const PAGES: Array<[string, () => React.ReactElement]> = [
  ["AI推論ログ", () => <AiInferenceLogsPage />],
  ["承認ポリシー", () => <ApprovalPoliciesPage />],
  ["債権年齢表", () => <ArAgingPage />],
  ["監査ログ", () => <AuditPage />],
  ["不正検知", () => <AuditDetectionPage />],
  ["銀行明細", () => <BankPage />],
  ["予算管理", () => <BudgetsPage />],
  ["ジョブ", () => <JobsPage />],
  ["運用モニタリング", () => <OpsPage />],
  ["支払申請", () => <PaymentsPage />],
  ["税務調整", () => <TaxAdjustmentsPage />],
  ["資金繰り予測", () => <TreasuryPage />],
];

beforeEach(() => {
  for (const fn of [apiGet, apiPost, apiPut, apiPatch, apiDelete]) fn.mockReset();
  // 呼ばれてしまった場合に unhandled rejection にせず、呼び出し記録だけ残す。
  apiGet.mockResolvedValue([]);
});

describe("権限ゼロのユーザーはデータを取得しない", () => {
  for (const [name, renderPage] of PAGES) {
    it(name, async () => {
      await act(async () => {
        render(renderPage());
      });

      expect(apiGet, `${name}: 権限が無いのに取得APIを呼んでいる`).not.toHaveBeenCalled();
      expect(apiPost).not.toHaveBeenCalled();
      expect(apiPut).not.toHaveBeenCalled();
      expect(apiPatch).not.toHaveBeenCalled();
      expect(apiDelete).not.toHaveBeenCalled();
    });
  }
});
