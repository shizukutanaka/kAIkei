import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

/**
 * 支払申請画面の振る舞いを固定する。
 *
 * 対象は「壊れても型検査やビルドでは気付けない」ロジック:
 * - 権限による表示制御（master:read が無ければ内容を出さない）
 * - ステータス別の操作ボタン（下書きは承認のみ、承認済みは実行のみ、実行済みは操作なし）
 *
 * 承認・実行の遷移はバックエンド側でも状態機械で守っているが、UIが誤ったボタンを
 * 出すと利用者は409エラーに突き当たる。表示条件そのものを固定しておく。
 */

const apiGet = vi.fn();
const apiPost = vi.fn();
let mockPermissions: string[] = [];

vi.mock("@/lib/api", () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
}));
vi.mock("@/lib/company-context", () => ({
  useCompany: () => ({ companyId: "company-1" }),
}));
vi.mock("@/lib/use-user", () => ({
  useUser: () => ({ user: { permissions: mockPermissions } }),
}));
vi.mock("@/components/page-layout", () => ({
  default: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));
vi.mock("@/components/skeleton", () => ({
  SkeletonTable: () => <div data-testid="skeleton" />,
}));

import PaymentsPage from "./page";

function paymentRow(overrides: Record<string, unknown> = {}) {
  return {
    payment_request_id: "req-1",
    company_id: "company-1",
    payment_date: "2026-06-30",
    payment_amount: "10000",
    dest_bank_code: "0001",
    dest_branch_code: "001",
    dest_account_type: "ordinary",
    dest_account_no: "1234567",
    dest_account_name_kana: "ﾃｽﾄﾀﾛｳ",
    status: "draft",
    ...overrides,
  };
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  mockPermissions = [];
});

describe("PaymentsPage 権限制御", () => {
  it("master:read が無ければ一覧を取得も表示もしない", async () => {
    mockPermissions = [];
    render(<PaymentsPage />);

    expect(screen.getByText(/権限がありません/)).toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("master:read だけなら作成ボタンを出さない", async () => {
    mockPermissions = ["master:read"];
    apiGet.mockResolvedValue([]);
    render(<PaymentsPage />);

    await waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /支払申請を作成/ })).not.toBeInTheDocument();
  });

  it("master:create があれば作成ボタンを出す", async () => {
    mockPermissions = ["master:read", "master:create"];
    apiGet.mockResolvedValue([]);
    render(<PaymentsPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /支払申請を作成/ })).toBeInTheDocument()
    );
  });
});

describe("PaymentsPage ステータス別の操作", () => {
  it("下書きには承認と取消を出し、実行は出さない", async () => {
    mockPermissions = ["master:read", "master:update"];
    apiGet.mockResolvedValue([paymentRow({ status: "draft" })]);
    render(<PaymentsPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: /承認/ })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /取消/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /実行/ })).not.toBeInTheDocument();
  });

  it("承認済みには実行と取消を出し、承認は出さない", async () => {
    mockPermissions = ["master:read", "master:update"];
    apiGet.mockResolvedValue([paymentRow({ status: "approved" })]);
    render(<PaymentsPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: /実行/ })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /取消/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /承認/ })).not.toBeInTheDocument();
  });

  it("実行済みには遷移操作を一切出さない", async () => {
    mockPermissions = ["master:read", "master:update"];
    apiGet.mockResolvedValue([paymentRow({ status: "executed" })]);
    render(<PaymentsPage />);

    await waitFor(() => expect(screen.getByText("実行済み")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /承認/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /実行/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /取消/ })).not.toBeInTheDocument();
  });

  it("master:update が無ければ下書きでも操作を出さない", async () => {
    mockPermissions = ["master:read"];
    apiGet.mockResolvedValue([paymentRow({ status: "draft" })]);
    render(<PaymentsPage />);

    await waitFor(() => expect(screen.getByText("下書き")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /承認/ })).not.toBeInTheDocument();
  });
});

describe("PaymentsPage 表示", () => {
  it("取得失敗時はエラーを表示する", async () => {
    mockPermissions = ["master:read"];
    apiGet.mockRejectedValue(new Error("読み込みに失敗しました"));
    render(<PaymentsPage />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/失敗/));
  });

  it("0件のときは空状態を表示する", async () => {
    mockPermissions = ["master:read"];
    apiGet.mockResolvedValue([]);
    render(<PaymentsPage />);

    await waitFor(() =>
      expect(screen.getByText(/支払申請がありません/)).toBeInTheDocument()
    );
  });
});
