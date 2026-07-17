import { describe, expect, it } from "vitest";
import { formatYen } from "./format";

describe("formatYen", () => {
  it("formats numeric strings with grouping", () => {
    expect(formatYen("1234567")).toBe("¥1,234,567");
  });

  it("formats numbers", () => {
    expect(formatYen(11000)).toBe("¥11,000");
  });

  it("returns dash for null/undefined/empty", () => {
    expect(formatYen(null)).toBe("-");
    expect(formatYen(undefined)).toBe("-");
    expect(formatYen("")).toBe("-");
  });

  it("passes through non-numeric strings", () => {
    expect(formatYen("非公開")).toBe("非公開");
  });

  it("keeps decimals from string input", () => {
    expect(formatYen("1000.5")).toBe("¥1,000.5");
  });
});
