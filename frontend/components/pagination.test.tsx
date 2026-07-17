import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Pagination } from "./pagination";

describe("Pagination", () => {
  it("renders nothing when total is 0", () => {
    const { container } = render(
      <Pagination page={1} pageSize={10} total={0} onPageChange={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows all pages when total pages <= 7", () => {
    render(<Pagination page={1} pageSize={10} total={30} onPageChange={() => {}} />);
    expect(screen.getByRole("button", { name: "1ページ目" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3ページ目" })).toBeInTheDocument();
    expect(screen.queryByText("...")).not.toBeInTheDocument();
  });

  it("collapses middle pages with ellipsis when many pages", () => {
    render(<Pagination page={5} pageSize={10} total={200} onPageChange={() => {}} />);
    expect(screen.getByRole("button", { name: "1ページ目" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20ページ目" })).toBeInTheDocument();
    expect(screen.getAllByText("...").length).toBeGreaterThan(0);
  });

  it("calls onPageChange when a page number is clicked", () => {
    const onPageChange = vi.fn();
    render(<Pagination page={1} pageSize={10} total={30} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "2ページ目" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
