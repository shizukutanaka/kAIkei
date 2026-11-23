import { describe, expect, it } from "vitest";

import { BANK_COLUMN_FIELDS, buildColumnMap } from "./bank-import";

describe("buildColumnMap", () => {
  it("returns null when nothing is specified", () => {
    expect(buildColumnMap({})).toBeNull();
    expect(buildColumnMap({ date: "  ", deposit: "" })).toBeNull();
  });

  it("includes only non-empty trimmed values", () => {
    expect(buildColumnMap({ date: " 年月日 ", deposit: "入", withdrawal: "" })).toEqual({
      date: "年月日",
      deposit: "入",
    });
  });

  it("ignores keys that are not bank column fields", () => {
    expect(buildColumnMap({ unknown: "x", date: "日付" })).toEqual({ date: "日付" });
  });

  it("covers the canonical keys the backend accepts", () => {
    expect(BANK_COLUMN_FIELDS.map((f) => f.key)).toEqual([
      "date",
      "deposit",
      "withdrawal",
      "amount",
      "direction",
      "balance",
      "description",
      "counterparty",
    ]);
  });
});
