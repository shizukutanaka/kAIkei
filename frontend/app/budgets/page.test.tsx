import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * 予算管理画面の挙動を固定する。
 *
 * 予実分析は「どの科目が予算超過か」の判断に使われるため、超過の強調が外れると
 * 見落としに直結する。また削除ボタンは権限で隠れる必要がある（サーバ側で拒否
 * されるとしても、押せるボタンを出すこと自体が誤操作を誘発する）。
 */

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();
let mockPermissions: string[] = [];

vi.mock("@/lib/api", () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiDelete: (...args: unknown[]) => apiDelete(...args),
}));
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

import BudgetsPage from "./page";

const budget = {
  budget_id: "b1",
  company_id: "company-1",
  fiscal_year: 2026,
  name: "2026年度予算",
  status: "draft",
  lines: [{ budget_line_id: "l1", account_id: "a1", month: 4, budgeted_amount: "100000" }],
};

const variance = {
  budget_id: "b1",
  fiscal_year: 2026,
  budgeted_total: "100000",
  actual_total: "130000",
  variance_total: "-30000",
  execution_rate: "1.3",
  over_budget_count: 1,
  line_count: 2,
  lines: [
    {
      account_id: "a1",
      account_code: "5110",
      account_name: "旅費交通費",
      budgeted_amount: "40000",
      actual_amount: "70000",
      variance_amount: "-30000",
      variance_rate: "-0.75",
      execution_rate: "1.75",
      is_over_budget: true,
    },
    {
      account_id: "a2",
      account_code: "5210",
      account_name: "通信費",
      budgeted_amount: "60000",
      actual_amount: "60000",
      variance_amount: "0",
      variance_rate: "0",
      execution_rate: "1.0",
      is_over_budget: false,
    },
  ],
};

/** 一覧の初期ロード（予算＋勘定科目）を返す。 */
function mockList() {
  apiGet.mockImplementation((path: string) => {
    if (path === "/budgets") return Promise.resolve([budget]);
    if (path === "/masters") return Promise.resolve([{ account_id: "a1", account_code: "5110", account_name: "旅費交通費" }]);
    if (path.endsWith("/variance")) return Promise.resolve(variance);
    return Promise.reject(new Error(`unexpected path: ${path}`));
  });
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiDelete.mockReset();
  mockPermissions = ["master:read", "master:create", "master:delete"];
});

describe("BudgetsPage 権限制御", () => {
  it("master:read が無ければ内容を出さず、APIも呼ばない", () => {
    mockPermissions = [];
    render(<BudgetsPage />);
    expect(screen.getByText(/権限がありません/)).toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("master:delete が無ければ削除ボタンを出さない", async () => {
    mockPermissions = ["master:read"];
    mockList();
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText("2026年度予算")).toBeInTheDocument());
    expect(screen.queryByLabelText("2026年度予算 を削除")).not.toBeInTheDocument();
    expect(screen.getByLabelText("2026年度予算 の予実分析")).toBeInTheDocument();
  });

  it("master:create が無ければ新規作成を出さない", async () => {
    mockPermissions = ["master:read"];
    mockList();
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText("2026年度予算")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /予算を新規作成/ })).not.toBeInTheDocument();
  });
});

describe("BudgetsPage 予実分析", () => {
  it("予実ボタンを押すまで分析APIを呼ばない", async () => {
    mockList();
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText("2026年度予算")).toBeInTheDocument());
    expect(apiGet).not.toHaveBeenCalledWith("/budgets/b1/variance");
  });

  it("予算超過の科目だけを強調する", async () => {
    mockList();
    const { container } = render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText("2026年度予算")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("2026年度予算 の予実分析"));

    await waitFor(() => expect(screen.getByText(/旅費交通費/)).toBeInTheDocument());

    // 超過行(旅費交通費)には強調が付き、非超過行(通信費)には付かないこと。
    const rows = Array.from(container.querySelectorAll("tbody tr"));
    const over = rows.find((r) => r.textContent?.includes("旅費交通費"));
    const under = rows.find((r) => r.textContent?.includes("通信費"));
    expect(over?.className).toContain("bg-destructive/5");
    expect(under?.className).not.toContain("bg-destructive/5");
  });

  it("執行率を百分率で表示する", async () => {
    mockList();
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText("2026年度予算")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("2026年度予算 の予実分析"));

    // execution_rate は比率(1.3)で返るので、130.0% と表示されること。
    await waitFor(() => expect(screen.getByText(/130\.0% \/ 1件/)).toBeInTheDocument());
    expect(screen.getByText("175.0%")).toBeInTheDocument();
  });

  it("分析の取得に失敗したらエラーを出す", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/budgets") return Promise.resolve([budget]);
      if (path === "/masters") return Promise.resolve([]);
      return Promise.reject(new Error("予実分析の取得に失敗しました"));
    });
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText("2026年度予算")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("2026年度予算 の予実分析"));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/失敗/));
  });
});

describe("BudgetsPage 一覧", () => {
  it("予算が無ければ空状態を出す", async () => {
    apiGet.mockImplementation((path: string) =>
      path === "/budgets" ? Promise.resolve([]) : Promise.resolve([])
    );
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByText(/予算がありません/)).toBeInTheDocument());
  });

  it("読み込み失敗時はエラーを出す", async () => {
    apiGet.mockRejectedValue(new Error("読み込みに失敗しました"));
    render(<BudgetsPage />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/失敗/));
  });
});
