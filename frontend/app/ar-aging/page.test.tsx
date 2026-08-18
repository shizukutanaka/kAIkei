import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * 債権年齢表の表示を固定する。
 *
 * この画面は滞留債権の回収管理と貸倒引当金の見積り基礎資料として使われるため、
 * 「どの区分にいくら入っているか」の対応が崩れると会計判断を誤らせる。
 * 区分の並びと金額の対応、90日超の強調、権限制御を固定する。
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

import ArAgingPage from "./page";

const buckets = (over90 = "0") => ({
  not_due: "1000",
  overdue_1_30: "2000",
  overdue_31_60: "3000",
  overdue_61_90: "4000",
  overdue_over_90: over90,
});

function aging(overrides: Record<string, unknown> = {}) {
  return {
    company_id: "company-1",
    as_of: "2026-06-30",
    buckets: buckets(),
    total: "10000",
    overdue_total: "9000",
    invoice_count: 4,
    partners: [
      {
        partner_id: "p1",
        partner_name: "大口物産",
        buckets: buckets(),
        total: "10000",
        invoice_count: 4,
        oldest_days_overdue: 45,
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  apiGet.mockReset();
  mockPermissions = ["report:read"];
});

describe("ArAgingPage 権限制御", () => {
  it("report:read が無ければ内容を出さない", () => {
    mockPermissions = [];
    render(<ArAgingPage />);
    expect(screen.getByText(/権限がありません/)).toBeInTheDocument();
  });
});

describe("ArAgingPage 集計の表示", () => {
  it("集計するまではAPIを呼ばない（基準日を選ばせるため）", () => {
    render(<ArAgingPage />);
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("区分の見出しを実務標準の順序で表示する", async () => {
    apiGet.mockResolvedValue(aging());
    render(<ArAgingPage />);
    fireEvent.click(screen.getByRole("button", { name: /集計/ }));

    await waitFor(() => expect(screen.getByText("大口物産")).toBeInTheDocument());
    for (const label of ["期日未到来", "1-30日超過", "31-60日超過", "61-90日超過", "90日超過"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("最長延滞日数を表示する", async () => {
    apiGet.mockResolvedValue(aging());
    render(<ArAgingPage />);
    fireEvent.click(screen.getByRole("button", { name: /集計/ }));

    await waitFor(() => expect(screen.getByText(/45日/)).toBeInTheDocument());
  });

  it("未回収が無ければ空状態を出す", async () => {
    apiGet.mockResolvedValue(aging({ partners: [], invoice_count: 0, total: "0" }));
    render(<ArAgingPage />);
    fireEvent.click(screen.getByRole("button", { name: /集計/ }));

    await waitFor(() =>
      expect(screen.getByText(/未回収の請求書はありません/)).toBeInTheDocument()
    );
  });

  it("取得失敗時はエラーを表示する", async () => {
    apiGet.mockRejectedValue(new Error("債権年齢表の取得に失敗しました"));
    render(<ArAgingPage />);
    fireEvent.click(screen.getByRole("button", { name: /集計/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/失敗/));
  });

  it("基準日をAPIに渡す", async () => {
    apiGet.mockResolvedValue(aging());
    render(<ArAgingPage />);
    fireEvent.change(screen.getByLabelText("基準日"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: /集計/ }));

    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(
        "/reports/ar-aging",
        expect.objectContaining({ as_of: "2026-03-31" })
      )
    );
  });
});
