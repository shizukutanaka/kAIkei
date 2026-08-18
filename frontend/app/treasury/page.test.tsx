import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * 資金繰り予測の表示を固定する。
 *
 * 純キャッシュフローの符号は「資金が足りるか」の判断そのものなので、
 * マイナスが目立たなくなる変更が入ると意思決定を誤らせる。符号による強調と
 * 期間別の対応を固定する。
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

import TreasuryPage from "./page";

// 7日は黒字 +7777、30日は赤字 -3333。金額を重複させないことで
// 「どちらが強調されたか」を文字列で判定できるようにする。
function forecast() {
  return {
    company_id: "company-1",
    as_of: "2026-06-30",
    buckets: [
      { horizon_days: 7, inflows: "17777", outflows: "10000", net_cashflow: "7777" },
      { horizon_days: 30, inflows: "20000", outflows: "23333", net_cashflow: "-3333" },
    ],
  };
}

beforeEach(() => {
  apiGet.mockReset();
  mockPermissions = ["report:read"];
});

describe("TreasuryPage", () => {
  it("report:read が無ければ内容を出さない", () => {
    mockPermissions = [];
    render(<TreasuryPage />);
    expect(screen.getByText(/権限がありません/)).toBeInTheDocument();
  });

  it("予測するまではAPIを呼ばない", () => {
    render(<TreasuryPage />);
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("期間別の見出しを表示する", async () => {
    apiGet.mockResolvedValue(forecast());
    render(<TreasuryPage />);
    fireEvent.click(screen.getByRole("button", { name: /予測/ }));

    await waitFor(() => expect(screen.getAllByText(/今後 7 日/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/今後 30 日/).length).toBeGreaterThan(0);
  });

  it("純キャッシュフローがマイナスの期間だけを強調する", async () => {
    apiGet.mockResolvedValue(forecast());
    const { container } = render(<TreasuryPage />);
    fireEvent.click(screen.getByRole("button", { name: /予測/ }));

    await waitFor(() => expect(container.querySelectorAll(".text-destructive").length).toBeGreaterThan(0));

    // 符号で強調が切り替わること（全部に付くのはNG）。
    const emphasized = Array.from(container.querySelectorAll(".text-destructive")).map((e) => e.textContent ?? "");
    expect(emphasized.some((t) => t.includes("3,333"))).toBe(true);
    expect(emphasized.every((t) => !t.includes("7,777"))).toBe(true);

    const positive = Array.from(container.querySelectorAll(".text-green-700"));
    expect(positive.length).toBeGreaterThan(0);
  });

  it("取得失敗時はエラーを表示する", async () => {
    apiGet.mockRejectedValue(new Error("資金繰り予測の取得に失敗しました"));
    render(<TreasuryPage />);
    fireEvent.click(screen.getByRole("button", { name: /予測/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/失敗/));
  });

  it("基準日をAPIへ渡す", async () => {
    apiGet.mockResolvedValue(forecast());
    render(<TreasuryPage />);
    fireEvent.change(screen.getByLabelText("基準日"), { target: { value: "2026-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: /予測/ }));

    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(
        "/treasury/cashflow-forecast",
        expect.objectContaining({ as_of: "2026-03-31" })
      )
    );
  });
});
