"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { SkeletonTable } from "@/components/skeleton";
import { Users, Plus, Calculator, Trash2, FileText, Download } from "lucide-react";

interface Employee {
  employee_id: string;
  company_id: string;
  employee_code: string;
  employee_name: string;
  department: string | null;
  position: string | null;
  employment_type: string;
  base_salary: string;
  hourly_rate: string;
  hire_date: string;
  termination_date: string | null;
  is_active: boolean;
}

interface PayrollRecord {
  payroll_id: string;
  employee_id: string;
  company_id: string;
  payroll_year: number;
  payroll_month: number;
  base_salary: string;
  overtime_hours: string;
  overtime_pay: string;
  total_gross: string;
  income_tax: string;
  social_insurance: string;
  total_deductions: string;
  net_pay: string;
  status: string;
  employee_name: string | null;
}

const EMPLOYMENT_TYPE_LABELS: Record<string, string> = {
  full_time: "正社員",
  part_time: "パート",
  contract: "契約社員",
  dispatch: "派遣",
};

export default function PayrollPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const perms = user?.permissions ?? [];
  const canCreate = perms.includes("master:create");
  const canDelete = perms.includes("master:delete");
  const canCalculate = perms.includes("journal:create");

  const [tab, setTab] = useState<"employees" | "payroll">("employees");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [payrollRecords, setPayrollRecords] = useState<PayrollRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    employee_code: "",
    employee_name: "",
    department: "",
    position: "",
    employment_type: "full_time",
    base_salary: "",
    hourly_rate: "",
    hire_date: new Date().toISOString().split("T")[0],
  });
  const [payrollYear, setPayrollYear] = useState(new Date().getFullYear().toString());
  const [payrollMonth, setPayrollMonth] = useState((new Date().getMonth() + 1).toString());
  const [overtimeMap, setOvertimeMap] = useState<Record<string, string>>({});
  const [calculating, setCalculating] = useState(false);

  const fetchEmployees = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<Employee[]>("/payroll/employees", { company_id: companyId });
      setEmployees(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const fetchPayrollRecords = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<PayrollRecord[]>("/payroll/records", {
        company_id: companyId,
        payroll_year: payrollYear,
        payroll_month: payrollMonth,
      });
      setPayrollRecords(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "employees" && companyId) fetchEmployees();
    if (tab === "payroll" && companyId) {
      if (employees.length === 0) fetchEmployees();
      fetchPayrollRecords();
    }
  }, [companyId, tab, payrollYear, payrollMonth]);

  const handleCreateEmployee = async () => {
    if (!formData.employee_code || !formData.employee_name) {
      toast("従業員コードと氏名は必須です", "warning");
      return;
    }
    setLoading(true);
    try {
      await apiPost("/payroll/employees", {
        company_id: companyId,
        ...formData,
        base_salary: parseFloat(formData.base_salary) || 0,
        hourly_rate: parseFloat(formData.hourly_rate) || 0,
      });
      setShowForm(false);
      setFormData({
        employee_code: "",
        employee_name: "",
        department: "",
        position: "",
        employment_type: "full_time",
        base_salary: "",
        hourly_rate: "",
        hire_date: new Date().toISOString().split("T")[0],
      });
      toast("従業員を登録しました", "success");
      await fetchEmployees();
    } catch (err) {
      toast(err instanceof Error ? err.message : "登録に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteEmployee = async (empId: string) => {
    if (!confirm("この従業員を削除しますか？")) return;
    try {
      await apiDelete(`/payroll/employees/${empId}`);
      toast("従業員を削除しました", "success");
      await fetchEmployees();
    } catch (err) {
      toast(err instanceof Error ? err.message : "削除に失敗しました", "error");
    }
  };

  const handleCalculate = async () => {
    setCalculating(true);
    setError("");
    try {
      const otMap: Record<string, number> = {};
      for (const [empId, hours] of Object.entries(overtimeMap)) {
        if (hours && parseFloat(hours) > 0) {
          otMap[empId] = parseFloat(hours);
        }
      }
      const data = await apiPost<PayrollRecord[]>("/payroll/calculate", {
        company_id: companyId,
        payroll_year: parseInt(payrollYear),
        payroll_month: parseInt(payrollMonth),
        overtime_hours: otMap,
      });
      setPayrollRecords(data);
      toast(`${data.length}件の給与を計算しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "計算に失敗しました", "error");
    } finally {
      setCalculating(false);
    }
  };

  const totalGross = payrollRecords.reduce((sum, r) => sum + parseFloat(r.total_gross), 0);
  const totalDeductions = payrollRecords.reduce((sum, r) => sum + parseFloat(r.total_deductions), 0);
  const totalNet = payrollRecords.reduce((sum, r) => sum + parseFloat(r.net_pay), 0);

  const handleDownloadPayslip = async (payrollId: string, empName: string) => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const response = await fetch(`${apiBase}/payroll/payslip/${payrollId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("取得に失敗しました");
      const text = await response.text();
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `payslip_${empName}_${payrollYear}${payrollMonth}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast("給与明細をダウンロードしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ダウンロードに失敗しました", "error");
    }
  };

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <Users className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">給与</h1>
      </div>

      {!companyId && (
        <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          サイドバーで会社を選択してください。
        </div>
      )}

      <div className="mb-6 flex gap-2 border-b">
        <button
          onClick={() => setTab("employees")}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === "employees" ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}
        >
          従業員マスタ
        </button>
        <button
          onClick={() => setTab("payroll")}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === "payroll" ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}
        >
          給与計算
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {tab === "employees" && (
        <>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{employees.length}件の従業員</p>
            {canCreate && (
              <button
                onClick={() => setShowForm(!showForm)}
                className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              >
                <Plus className="h-4 w-4" />
                従業員追加
              </button>
            )}
          </div>

          {showForm && (
            <div className="mb-6 rounded-lg border bg-card p-6">
              <h2 className="mb-4 text-lg font-semibold">新規従業員登録</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">従業員コード</label>
                  <input type="text" value={formData.employee_code} onChange={(e) => setFormData({ ...formData, employee_code: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">氏名</label>
                  <input type="text" value={formData.employee_name} onChange={(e) => setFormData({ ...formData, employee_name: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">部署</label>
                  <input type="text" value={formData.department} onChange={(e) => setFormData({ ...formData, department: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">役職</label>
                  <input type="text" value={formData.position} onChange={(e) => setFormData({ ...formData, position: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">雇用形態</label>
                  <select value={formData.employment_type} onChange={(e) => setFormData({ ...formData, employment_type: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                    {Object.entries(EMPLOYMENT_TYPE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">入社日</label>
                  <input type="date" value={formData.hire_date} onChange={(e) => setFormData({ ...formData, hire_date: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">基本給（月額）</label>
                  <input type="number" value={formData.base_salary} onChange={(e) => setFormData({ ...formData, base_salary: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">時給</label>
                  <input type="number" value={formData.hourly_rate} onChange={(e) => setFormData({ ...formData, hourly_rate: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
                </div>
              </div>
              <div className="mt-4 flex gap-2">
                <button onClick={handleCreateEmployee} disabled={loading} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                  {loading ? "登録中..." : "登録"}
                </button>
                <button onClick={() => setShowForm(false)} className="rounded-md border px-4 py-2 text-sm">
                  キャンセル
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <SkeletonTable rows={5} columns={6} />
          ) : employees.length > 0 ? (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">従業員コード</th>
                    <th className="px-4 py-3 text-left font-medium">氏名</th>
                    <th className="px-4 py-3 text-left font-medium">部署</th>
                    <th className="px-4 py-3 text-left font-medium">雇用形態</th>
                    <th className="px-4 py-3 text-right font-medium">基本給</th>
                    <th className="px-4 py-3 text-center font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map((e) => (
                    <tr key={e.employee_id} className="border-t hover:bg-muted/30">
                      <td className="px-4 py-3 font-mono">{e.employee_code}</td>
                      <td className="px-4 py-3">{e.employee_name}</td>
                      <td className="px-4 py-3">{e.department || "-"}</td>
                      <td className="px-4 py-3">{EMPLOYMENT_TYPE_LABELS[e.employment_type] || e.employment_type}</td>
                      <td className="px-4 py-3 text-right">¥{parseInt(e.base_salary).toLocaleString()}</td>
                      <td className="px-4 py-3 text-center">
                        {canDelete && (
                          <button
                            onClick={() => handleDeleteEmployee(e.employee_id)}
                            className="flex items-center gap-1 rounded border border-destructive/50 px-2 py-1 text-xs text-destructive hover:bg-destructive/10 mx-auto"
                          >
                            <Trash2 className="h-3 w-3" />
                            削除
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-center text-sm text-muted-foreground">従業員データがありません</p>
          )}
        </>
      )}

      {tab === "payroll" && (
        <>
          <div className="mb-4 flex items-center justify-between rounded-lg border bg-card p-4">
            <div className="flex items-center gap-4">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">年</label>
                <input type="number" value={payrollYear} onChange={(e) => setPayrollYear(e.target.value)} className="w-24 rounded-md border px-3 py-1.5 text-sm" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">月</label>
                <select value={payrollMonth} onChange={(e) => setPayrollMonth(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <option key={i + 1} value={String(i + 1)}>{i + 1}月</option>
                  ))}
                </select>
              </div>
            </div>
            {canCalculate && (
              <button
                onClick={handleCalculate}
                disabled={calculating || !companyId}
                className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                <Calculator className="h-4 w-4" />
                {calculating ? "計算中..." : "給与計算実行"}
              </button>
            )}
          </div>

          {canCalculate && employees.length > 0 && (
            <div className="mb-4 rounded-lg border bg-card p-4">
              <h3 className="mb-3 text-sm font-semibold">残業時間入力</h3>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
                {employees.map((e) => (
                  <div key={e.employee_id} className="flex items-center gap-2">
                    <label className="text-xs text-muted-foreground whitespace-nowrap">{e.employee_name}</label>
                    <input
                      type="number"
                      min="0"
                      step="0.5"
                      placeholder="0"
                      value={overtimeMap[e.employee_id] || ""}
                      onChange={(ev) => setOvertimeMap({ ...overtimeMap, [e.employee_id]: ev.target.value })}
                      className="w-20 rounded-md border px-2 py-1 text-sm"
                    />
                    <span className="text-xs text-muted-foreground">h</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading ? (
            <SkeletonTable rows={5} columns={8} />
          ) : payrollRecords.length > 0 ? (
            <>
              <div className="overflow-hidden rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">従業員</th>
                      <th className="px-4 py-3 text-right font-medium">基本給</th>
                      <th className="px-4 py-3 text-right font-medium">残業代</th>
                      <th className="px-4 py-3 text-right font-medium">総支給額</th>
                      <th className="px-4 py-3 text-right font-medium">源泉所得税</th>
                      <th className="px-4 py-3 text-right font-medium">社会保険料</th>
                      <th className="px-4 py-3 text-right font-medium">差引合計</th>
                      <th className="px-4 py-3 text-center font-medium">ステータス</th>
                      <th className="px-4 py-3 text-center font-medium">明細</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payrollRecords.map((r) => (
                      <tr key={r.payroll_id} className="border-t hover:bg-muted/30">
                        <td className="px-4 py-3">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                        <td className="px-4 py-3 text-right">¥{parseInt(r.base_salary).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right">¥{parseInt(r.overtime_pay).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right font-medium">¥{parseInt(r.total_gross).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-red-600">¥{parseInt(r.income_tax).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-red-600">¥{parseInt(r.social_insurance).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right font-bold">¥{parseInt(r.net_pay).toLocaleString()}</td>
                        <td className="px-4 py-3 text-center">
                          <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                            {r.status === "calculated" ? "計算済" : r.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => handleDownloadPayslip(r.payroll_id, r.employee_name || r.employee_id.slice(0, 8))}
                            className="flex items-center gap-1 rounded border px-2 py-1 text-xs hover:bg-accent mx-auto"
                            title="給与明細ダウンロード"
                          >
                            <Download className="h-3 w-3" />
                            明細
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 bg-muted/30 font-bold">
                      <td className="px-4 py-3">合計</td>
                      <td colSpan={2} />
                      <td className="px-4 py-3 text-right">¥{totalGross.toLocaleString()}</td>
                      <td colSpan={2} />
                      <td className="px-4 py-3 text-right">¥{totalNet.toLocaleString()}</td>
                      <td />
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-4">
                <div className="rounded-lg border bg-card p-4">
                  <p className="text-xs text-muted-foreground">総支給額合計</p>
                  <p className="text-xl font-bold">¥{totalGross.toLocaleString()}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                  <p className="text-xs text-muted-foreground">控除額合計</p>
                  <p className="text-xl font-bold text-red-600">¥{totalDeductions.toLocaleString()}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                  <p className="text-xs text-muted-foreground">差引支給額合計</p>
                  <p className="text-xl font-bold text-green-600">¥{totalNet.toLocaleString()}</p>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
              <FileText className="mb-3 h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {companyId ? "給与データがありません。給与計算を実行してください。" : "会社を選択してください。"}
              </p>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}
