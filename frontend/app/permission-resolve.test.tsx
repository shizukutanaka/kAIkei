import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";

/**
 * 権限が非同期に確定したあとで、ちゃんとデータを取りに行くことを固定する。
 *
 * `useUser` は `/rbac/me` を叩いて解決するため、マウント直後は user が null で
 * 権限フラグは false になる。取得の useEffect が権限フラグを依存配列に持って
 * いないと、初回だけ「権限なし」として素通りし、権限が確定しても**二度と
 * 再実行されない**。結果、正当な権限を持つユーザーに空の画面が出続ける。
 *
 * 「権限が無いとき呼ばない」(permission-gate.test.tsx) と対になる検証で、
 * ゲートを足したときに取得そのものを殺していないことを担保する。
 */

const apiGet = vi.fn();

vi.mock("@/lib/api", () => ({
  apiGet: (...a: unknown[]) => apiGet(...a),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));
vi.mock("@/lib/company-context", () => ({ useCompany: () => ({ companyId: "company-1" }) }));

// 実物と同じく「最初は null、あとから解決」する useUser。
vi.mock("@/lib/use-user", () => ({
  useUser: () => {
    const [user, setUser] = useState<{ permissions: string[] } | null>(null);
    useEffect(() => {
      const id = setTimeout(
        () =>
          setUser({
            permissions: [
              "master:read",
              "master:create",
              "master:delete",
              "report:read",
              "journal:read",
              "journal:update",
              "integration:import",
              "ai:review",
              "audit:review",
            ],
          }),
        0
      );
      return () => clearTimeout(id);
    }, []);
    return { user, loading: user === null };
  },
}));
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
import AuditPage from "./audit/page";
import AuditDetectionPage from "./audit-detection/page";
import BankPage from "./bank/page";
import BudgetsPage from "./budgets/page";
import JobsPage from "./jobs/page";
import OpsPage from "./ops/page";
import TaxAdjustmentsPage from "./tax-adjustments/page";

/** マウント時に自動取得する画面（ボタン操作を必要としないもの）。 */
const AUTO_LOADING_PAGES: Array<[string, () => React.ReactElement]> = [
  ["AI推論ログ", () => <AiInferenceLogsPage />],
  ["承認ポリシー", () => <ApprovalPoliciesPage />],
  ["監査ログ", () => <AuditPage />],
  ["不正検知", () => <AuditDetectionPage />],
  ["銀行明細", () => <BankPage />],
  ["予算管理", () => <BudgetsPage />],
  ["ジョブ", () => <JobsPage />],
  ["運用モニタリング", () => <OpsPage />],
  ["税務調整", () => <TaxAdjustmentsPage />],
];

const emptyHealth = { total: 0, failed: 0, dead: 0, failure_rate: 0, level: "healthy" };

/** 画面が描画で参照する形だけ満たす空レスポンス。中身は本テストの関心事ではない。 */
function emptyResponse(path: string): unknown {
  if (path === "/ops/health") {
    return {
      company_id: "company-1",
      overall_level: "healthy",
      jobs: emptyHealth,
      webhooks: emptyHealth,
      overdue_tasks: 0,
    };
  }
  if (path === "/audit/logs") return { items: [], total: 0, page: 1, page_size: 50 };
  if (path === "/ai-inference-logs/stats") {
    return { total: 0, applied: 0, acceptance_rate: 0, corrected: 0, correction_rate: 0, avg_confidence: 0 };
  }
  return [];
}

beforeEach(() => {
  apiGet.mockReset();
  apiGet.mockImplementation((path: string) => Promise.resolve(emptyResponse(path)));
});

describe("権限が後から確定したら取得をやり直す", () => {
  for (const [name, renderPage] of AUTO_LOADING_PAGES) {
    it(name, async () => {
      render(renderPage());

      await waitFor(
        () => expect(apiGet, `${name}: 権限確定後も取得されないままになっている`).toHaveBeenCalled(),
        { timeout: 2000 }
      );
    });
  }
});
