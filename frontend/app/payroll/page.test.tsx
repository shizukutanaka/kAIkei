import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * 給与計算結果の表示を固定する。
 *
 * 源泉所得税と社会保険料は、法定の算出方法（税額表・標準報酬月額の等級・
 * 都道府県別料率）が未実装で概算のまま返る。概算だと分からないまま給与明細や
 * 納付額に使われると実害が出るため、警告が必ず画面に出ることを固定する。
 */

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();
let mockPermissions: string[] = [];

vi.mock("@/lib/api", () => ({
  apiGet: (...a: unknown[]) => apiGet(...a),
  apiPost: (...a: unknown[]) => apiPost(...a),
  apiDelete: (...a: unknown[]) => apiDelete(...a),
}));
vi.mock("@/lib/company-context", () => ({ useCompany: () => ({ companyId: "company-1" }) }));
vi.mock("@/lib/use-user", () => ({ useUser: () => ({ user: { permissions: mockPermissions } }) }));
// 計算実行前に確認ダイアログを挟む。ここで検証したいのは計算後の表示なので
// 常に承認する。
vi.mock("@/components/confirm-dialog", () => ({
  useConfirm: () => ({ confirm: () => Promise.resolve(true) }),
}));
vi.mock("@/components/toast", () => ({ useToast: () => ({ toast: () => {} }) }));
vi.mock("@/components/page-layout", () => ({
  default: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

import PayrollPage from "./page";

const employee = {
  employee_id: "e1",
  company_id: "company-1",
  employee_code: "E-001",
  employee_name: "残業 太郎",
  employment_type: "full_time",
  base_salary: "300000",
  hourly_rate: "2000",
  hire_date: "2024-04-01",
  is_active: true,
};

// バックエンドが返す文言（app/api/v1/endpoints/payroll.py の PAYROLL_ESTIMATE_NOTICE）。
// 社会保険料は等級ベースで正しく計算されるようになったため、概算は源泉所得税のみ。
const NOTICE =
  "源泉所得税は概算です（給与所得の源泉徴収税額表・扶養親族等の数が未対応）。" +
  "給与明細の確定や納付額の算出にはそのまま使用しないでください。";

function record(overrides: Record<string, unknown> = {}) {
  return {
    payroll_id: "p1",
    employee_id: "e1",
    company_id: "company-1",
    payroll_year: 2026,
    payroll_month: 4,
    base_salary: "300000",
    overtime_hours: "80",
    overtime_pay: "210000",
    total_gross: "510000",
    income_tax: "25500",
    social_insurance: "76500",
    total_deductions: "102000",
    net_pay: "408000",
    status: "calculated",
    employee_name: "残業 太郎",
    estimated_fields: ["income_tax"],
    estimate_notice: NOTICE,
    ...overrides,
  };
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiDelete.mockReset();
  mockPermissions = ["journal:create", "journal:read", "master:read"];
  apiGet.mockImplementation((path: string) => {
    if (path === "/payroll/employees") {
      return Promise.resolve({ items: [employee], total: 1, page: 1, page_size: 50 });
    }
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 });
  });
});

/** 給与計算タブを開く（既定は従業員マスタタブ）。 */
async function openPayrollTab() {
  render(<PayrollPage />);
  await waitFor(() => expect(screen.getByText("残業 太郎")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("tab", { name: "給与計算" }));
}

/** 金額は「¥」と数値が別テキストノードに分かれるため、セル単位で照合する。
 *  同じ金額のセルが複数あり得る（合計行等）ので件数は問わない。 */
function cells(text: string) {
  return screen.getAllByText((_, el) => el?.tagName === "TD" && el.textContent === text);
}

async function calculate() {
  await openPayrollTab();
  fireEvent.click(await screen.findByRole("button", { name: /給与計算実行/ }));
}

describe("PayrollPage 概算の明示", () => {
  it("概算である旨の警告を表示する", async () => {
    apiPost.mockResolvedValue([record()]);
    await calculate();

    await waitFor(() => expect(screen.getByRole("note")).toBeInTheDocument());
    expect(screen.getByRole("note")).toHaveTextContent(/概算/);
    expect(screen.getByRole("note")).toHaveTextContent(/納付額/);
    // 社会保険料は等級ベースで計算されるようになったので、警告に含めない。
    expect(screen.getByRole("note")).not.toHaveTextContent(/社会保険料/);
  });

  it("概算の通知が無ければ警告を出さない（法定計算に対応したとき）", async () => {
    apiPost.mockResolvedValue([record({ estimate_notice: null, estimated_fields: [] })]);
    await calculate();

    await waitFor(() => expect(cells("¥510,000").length).toBeGreaterThan(0));
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});

describe("PayrollPage 計算結果", () => {
  it("60時間超の割増を含む支給額をそのまま表示する", async () => {
    apiPost.mockResolvedValue([record()]);
    await calculate();

    // 一律1.25倍なら 200,000。法定どおりなら 210,000。
    await waitFor(() => expect(cells("¥210,000").length).toBeGreaterThan(0));
    expect(cells("¥408,000").length).toBeGreaterThan(0);
  });

  it("journal:create が無ければ計算を実行させない", async () => {
    mockPermissions = ["journal:read", "master:read"];
    await openPayrollTab();

    expect(screen.queryByRole("button", { name: /給与計算実行/ })).not.toBeInTheDocument();
  });
});
