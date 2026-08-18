import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { EstimateNotice } from "./estimate-notice";

/**
 * 「概算です」の警告は、給与明細・賞与・消費税申告のいずれでも
 * 利用者の目に入らなければ意味がない。サーバが通知を返したら必ず出ること、
 * 法定計算に対応したら（通知が無くなったら）消えることを固定する。
 */
describe("EstimateNotice", () => {
  it("通知があれば表示する", () => {
    render(<EstimateNotice notice="源泉所得税は概算です。" />);

    expect(screen.getByRole("note")).toHaveTextContent("源泉所得税は概算です。");
  });

  it("通知が無ければ何も出さない（法定計算に対応したとき）", () => {
    const { container } = render(<EstimateNotice notice={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("undefined でも落ちない", () => {
    const { container } = render(<EstimateNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("空文字は通知なしとして扱う", () => {
    const { container } = render(<EstimateNotice notice="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
