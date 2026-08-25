import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * 会社セレクタの空状態を固定する。
 *
 * 会社が1社も無いと、company_id を要求する全ての画面が使えない。それにも
 * かかわらず、空状態は「UUIDを入力」と表示して**入手する方法の無い値**を
 * 求めていた（作成APIも存在しなかった）。登録直後の利用者がここで詰まる。
 */

const apiGet = vi.fn();
const apiPost = vi.fn();
const setCompanyId = vi.fn();

vi.mock("@/lib/api", () => ({
  apiGet: (...a: unknown[]) => apiGet(...a),
  apiPost: (...a: unknown[]) => apiPost(...a),
}));
vi.mock("@/lib/company-context", () => ({
  useCompany: () => ({ companyId: "", setCompanyId }),
}));

import CompanySelector from "./company-selector";

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  setCompanyId.mockReset();
});

describe("会社が無いとき", () => {
  beforeEach(() => {
    apiGet.mockResolvedValue([]);
  });

  it("UUIDの入力を求めない（入手する方法が無い）", async () => {
    render(<CompanySelector />);

    await waitFor(() => expect(screen.getByLabelText("会社名")).toBeInTheDocument());
    expect(screen.queryByPlaceholderText("UUIDを入力")).not.toBeInTheDocument();
  });

  it("会社を作成できる", async () => {
    apiPost.mockResolvedValue({
      company_id: "new-id",
      company_name: "デモ商事",
      company_code: "DEMO",
    });
    render(<CompanySelector />);

    await waitFor(() => expect(screen.getByLabelText("会社名")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("会社名"), { target: { value: "デモ商事" } });
    fireEvent.change(screen.getByLabelText("会社コード"), { target: { value: "DEMO" } });
    fireEvent.click(screen.getByRole("button", { name: /会社を作成/ }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/companies", {
        company_name: "デモ商事",
        company_code: "DEMO",
      })
    );
  });

  it("作成した会社をそのまま選択状態にする", async () => {
    apiPost.mockResolvedValue({
      company_id: "new-id",
      company_name: "デモ商事",
      company_code: "DEMO",
    });
    render(<CompanySelector />);

    await waitFor(() => expect(screen.getByLabelText("会社名")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("会社名"), { target: { value: "デモ商事" } });
    fireEvent.change(screen.getByLabelText("会社コード"), { target: { value: "DEMO" } });
    fireEvent.click(screen.getByRole("button", { name: /会社を作成/ }));

    await waitFor(() => expect(setCompanyId).toHaveBeenCalledWith("new-id"));
  });

  it("未入力では送信できない", async () => {
    render(<CompanySelector />);

    await waitFor(() => expect(screen.getByLabelText("会社名")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /会社を作成/ })).toBeDisabled();
  });

  it("作成に失敗したら理由を出す", async () => {
    apiPost.mockRejectedValue(new Error("会社コードが既に使われています"));
    render(<CompanySelector />);

    await waitFor(() => expect(screen.getByLabelText("会社名")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("会社名"), { target: { value: "デモ商事" } });
    fireEvent.change(screen.getByLabelText("会社コード"), { target: { value: "DEMO" } });
    fireEvent.click(screen.getByRole("button", { name: /会社を作成/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/既に使われています/));
  });
});

describe("会社があるとき", () => {
  it("選択肢を出し、作成フォームは出さない", async () => {
    apiGet.mockResolvedValue([
      { company_id: "c1", company_name: "既存商事", company_code: "EX1" },
    ]);
    render(<CompanySelector />);

    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    expect(screen.queryByLabelText("会社名")).not.toBeInTheDocument();
  });
});
