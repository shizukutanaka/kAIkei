import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

/**
 * 運用モニタリングの表示を固定する。
 *
 * この画面は「ジョブやWebhookが黙って壊れていないか」を見るための最後の砦なので、
 * 危険な状態が正常に見えてしまう変更は運用事故に直結する。レベルの表示語と
 * 未知レベルのフォールバック、権限ゲートを固定する。
 */

const apiGet = vi.fn();
let mockPermissions: string[] = [];

vi.mock("@/lib/api", () => ({ apiGet: (...args: unknown[]) => apiGet(...args) }));
vi.mock("@/lib/company-context", () => ({ useCompany: () => ({ companyId: "company-1" }) }));
vi.mock("@/lib/use-user", () => ({ useUser: () => ({ user: { permissions: mockPermissions } }) }));
vi.mock("@/components/page-layout", () => ({
  default: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

import OpsPage from "./page";

const summary = (level: string, over: Partial<Record<string, number>> = {}) => ({
  total: 100,
  failed: 3,
  dead: 1,
  failure_rate: 0.04,
  level,
  ...over,
});

function health(overrides: Record<string, unknown> = {}) {
  return {
    company_id: "company-1",
    overall_level: "healthy",
    jobs: summary("healthy"),
    webhooks: summary("healthy"),
    overdue_tasks: 0,
    ...overrides,
  };
}

beforeEach(() => {
  apiGet.mockReset();
  mockPermissions = ["master:read"];
});

describe("OpsPage", () => {
  it("master:read が無ければ内容を出さず、APIも呼ばない", () => {
    mockPermissions = [];
    render(<OpsPage />);
    expect(screen.getByText(/権限がありません/)).toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("総合ステータスと各カードを表示する", async () => {
    apiGet.mockResolvedValue(health());
    render(<OpsPage />);

    await waitFor(() => expect(screen.getByText(/総合ステータス: 正常/)).toBeInTheDocument());
    expect(screen.getByText("スケジュールジョブ")).toBeInTheDocument();
    expect(screen.getByText("Webhook配信")).toBeInTheDocument();
    expect(screen.getByText("期限超過タスク")).toBeInTheDocument();
  });

  it("critical を「危険」として表示する（正常に見せない）", async () => {
    apiGet.mockResolvedValue(
      health({ overall_level: "critical", jobs: summary("critical", { dead: 40, failure_rate: 0.4 }) })
    );
    render(<OpsPage />);

    await waitFor(() => expect(screen.getByText(/総合ステータス: 危険/)).toBeInTheDocument());
    expect(screen.queryByText(/総合ステータス: 正常/)).not.toBeInTheDocument();
    expect(screen.getByText("40.0%")).toBeInTheDocument();
  });

  it("未知のレベルでも落ちず、そのまま表示する", async () => {
    apiGet.mockResolvedValue(health({ overall_level: "unknown_level" }));
    render(<OpsPage />);

    await waitFor(() => expect(screen.getByText(/総合ステータス: unknown_level/)).toBeInTheDocument());
  });

  it("期限超過タスクがあれば件数を表示する", async () => {
    apiGet.mockResolvedValue(health({ overdue_tasks: 7 }));
    render(<OpsPage />);

    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
  });

  it("取得失敗時はエラーを表示する", async () => {
    apiGet.mockRejectedValue(new Error("運用状態の取得に失敗しました"));
    render(<OpsPage />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/失敗/));
  });
});
