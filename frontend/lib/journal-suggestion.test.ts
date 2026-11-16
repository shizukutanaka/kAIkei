import { describe, expect, it } from "vitest";
import {
  candidateEvidence,
  candidateToFormLines,
  confidencePercent,
  suggestionEmptyMessage,
  type JournalSuggestionCandidate,
  type JournalSuggestionResponse,
} from "./journal-suggestion";

const account = (code: string, name: string) => ({
  account_id: `id-${code}`,
  account_code: code,
  account_name: name,
});

const candidate = (
  overrides: Partial<JournalSuggestionCandidate> = {},
): JournalSuggestionCandidate => ({
  debit_accounts: [account("730", "地代家賃")],
  credit_accounts: [account("100", "普通預金")],
  confidence: 0.8,
  support: 4,
  exact_matches: 0,
  reliable: true,
  matched_features: [],
  ...overrides,
});

const response = (
  overrides: Partial<JournalSuggestionResponse> = {},
): JournalSuggestionResponse => ({
  status: "ok",
  trained_examples: 12,
  candidates: [candidate()],
  ...overrides,
});

describe("suggestionEmptyMessage", () => {
  it("returns null when candidates exist (ok)", () => {
    expect(suggestionEmptyMessage(response())).toBeNull();
  });

  it("explains insufficient data with the actual count and the minimum", () => {
    const message = suggestionEmptyMessage(
      response({ status: "insufficient_data", trained_examples: 3, candidates: [] }),
    );
    expect(message).toContain("学習データが不足");
    expect(message).toContain("3 件");
    expect(message).toContain("5 件");
  });

  it("explains no matching history with the trained count", () => {
    const message = suggestionEmptyMessage(
      response({ status: "no_matching_history", trained_examples: 42, candidates: [] }),
    );
    expect(message).toContain("42 件");
    expect(message).toContain("見つかりませんでした");
  });
});

describe("candidateEvidence", () => {
  it("always includes the support count", () => {
    expect(candidateEvidence(candidate({ support: 7 }))).toContain("過去の類似仕訳 7 件");
  });

  it("adds exact matches only when present", () => {
    expect(candidateEvidence(candidate({ exact_matches: 0 }))).not.toContain("完全一致");
    expect(candidateEvidence(candidate({ exact_matches: 2 }))).toContain("摘要が完全一致 2 件");
  });

  it("lists matched words when present", () => {
    expect(candidateEvidence(candidate({ matched_features: ["家賃", "振込"] }))).toContain(
      "一致した語: 家賃、振込",
    );
  });
});

describe("confidencePercent", () => {
  it("rounds to a whole percent", () => {
    expect(confidencePercent(candidate({ confidence: 0.666 }))).toBe(67);
    expect(confidencePercent(candidate({ confidence: 0.5 }))).toBe(50);
  });
});

describe("candidateToFormLines", () => {
  it("builds one debit and one credit line with resolved accounts", () => {
    const lines = candidateToFormLines(candidate(), 55000);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({
      debit_credit: "debit",
      account_id: "id-730",
      account_code: "730",
      account_name: "地代家賃",
      amount: "55000",
    });
    expect(lines[1]).toMatchObject({
      debit_credit: "credit",
      account_id: "id-100",
      amount: "55000",
    });
  });

  it("puts the total only on the first line of each side for multi-account combos", () => {
    const lines = candidateToFormLines(
      candidate({
        debit_accounts: [account("730", "地代家賃"), account("760", "雑費")],
        credit_accounts: [account("100", "普通預金"), account("210", "未払金")],
      }),
      80000,
    );
    expect(lines.map((l) => l.amount)).toEqual(["80000", "", "80000", ""]);
    expect(lines.map((l) => l.debit_credit)).toEqual(["debit", "debit", "credit", "credit"]);
  });

  it("leaves amounts blank when no total is known (never invents amounts)", () => {
    const lines = candidateToFormLines(candidate(), 0);
    expect(lines.every((l) => l.amount === "")).toBe(true);
  });
});
