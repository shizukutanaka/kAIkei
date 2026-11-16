import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import JournalSuggestionPanel from "./journal-suggestion-panel";
import { apiPost } from "@/lib/api";
import type { JournalSuggestionResponse } from "@/lib/journal-suggestion";

vi.mock("@/lib/api", () => ({
  apiPost: vi.fn(),
}));

const mockedApiPost = vi.mocked(apiPost);

const okResponse: JournalSuggestionResponse = {
  status: "ok",
  trained_examples: 12,
  candidates: [
    {
      debit_accounts: [{ account_id: "d1", account_code: "730", account_name: "地代家賃" }],
      credit_accounts: [{ account_id: "c1", account_code: "100", account_name: "普通預金" }],
      confidence: 0.8,
      support: 4,
      exact_matches: 1,
      reliable: true,
      matched_features: ["家賃"],
    },
    {
      debit_accounts: [{ account_id: "d2", account_code: "760", account_name: "雑費" }],
      credit_accounts: [{ account_id: "c1", account_code: "100", account_name: "普通預金" }],
      confidence: 0.2,
      support: 1,
      exact_matches: 0,
      reliable: false,
      matched_features: [],
    },
  ],
};

function renderPanel(onApply = vi.fn()) {
  render(
    <JournalSuggestionPanel
      companyId="company-1"
      description="事務所家賃の支払い"
      amount={55000}
      onApply={onApply}
    />,
  );
  return onApply;
}

describe("JournalSuggestionPanel", () => {
  beforeEach(() => {
    mockedApiPost.mockReset();
  });

  it("fetches suggestions for the selected company and current summary only", async () => {
    mockedApiPost.mockResolvedValue(okResponse);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /候補を表示/ }));
    await waitFor(() => expect(mockedApiPost).toHaveBeenCalledTimes(1));
    expect(mockedApiPost).toHaveBeenCalledWith("/ai/suggest-journal", {
      description: "事務所家賃の支払い",
      amount: 55000,
      company_id: "company-1",
    });
  });

  it("shows candidates with evidence and a strong/weak distinction", async () => {
    mockedApiPost.mockResolvedValue(okResponse);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /候補を表示/ }));

    expect(await screen.findByText(/730 地代家賃/)).toBeInTheDocument();
    expect(screen.getByText(/根拠が強い候補/)).toBeInTheDocument();
    expect(screen.getByText(/過去の類似仕訳 4 件/)).toBeInTheDocument();
    expect(screen.getByText(/摘要が完全一致 1 件/)).toBeInTheDocument();

    expect(screen.getByText(/根拠が弱い候補/)).toBeInTheDocument();
    expect(screen.getByText(/根拠が弱いため、科目が正しいか必ず確認してください/)).toBeInTheDocument();

    expect(screen.getByText(/自動では保存されません/)).toBeInTheDocument();
  });

  it("applies a candidate only when its button is clicked", async () => {
    mockedApiPost.mockResolvedValue(okResponse);
    const onApply = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /候補を表示/ }));
    await screen.findByText(/730 地代家賃/);
    expect(onApply).not.toHaveBeenCalled();

    const applyButtons = screen.getAllByRole("button", { name: /この候補を反映/ });
    fireEvent.click(applyButtons[0]);
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0][0].debit_accounts[0].account_code).toBe("730");
  });

  it("shows the reason instead of an empty list when data is insufficient", async () => {
    mockedApiPost.mockResolvedValue({
      status: "insufficient_data",
      trained_examples: 2,
      candidates: [],
    } satisfies JournalSuggestionResponse);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /候補を表示/ }));
    expect(await screen.findByText(/学習データが不足しています/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /この候補を反映/ })).not.toBeInTheDocument();
  });

  it("shows the reason when there is no matching history", async () => {
    mockedApiPost.mockResolvedValue({
      status: "no_matching_history",
      trained_examples: 30,
      candidates: [],
    } satisfies JournalSuggestionResponse);
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /候補を表示/ }));
    expect(await screen.findByText(/似た取引が見つかりませんでした/)).toBeInTheDocument();
  });

  it("surfaces API errors instead of failing silently", async () => {
    mockedApiPost.mockRejectedValue(new Error("権限がありません"));
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /候補を表示/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("権限がありません");
  });

  it("disables fetching until a summary is entered", () => {
    render(
      <JournalSuggestionPanel companyId="company-1" description="  " amount={0} onApply={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /候補を表示/ })).toBeDisabled();
    expect(screen.getByText(/摘要を入力すると候補を探せます/)).toBeInTheDocument();
  });
});
