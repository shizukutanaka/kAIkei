"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { SkeletonTable } from "@/components/skeleton";
import { CalendarClock, Calculator, CheckCircle, FileText, Download, Search } from "lucide-react";

interface YearEndAdjustment {
  adjustment_id: string;
  employee_id: string;
  company_id: string;
  adjustment_year: number;
  annual_salary: string;
  annual_bonus: string;
  total_gross: string;
  withholding_tax_total: string;
  estimated_annual_tax: string;
  social_insurance_total: string;
  dependents: number;
  dependent_deduction: string;
  adjustment_amount: string;
  status: string;
  employee_name: string | null;
}

interface Employee {
  employee_id: string;
  employee_name: string;
}

const STATUS_LABELS: Record<string, string> = {
  calculated: "計算済",
  approved: "確定済",
};

const STATUS_COLORS: Record<string, string> = {
  calculated: "bg-blue-100 text-blue-700",
  approved: "bg-green-100 text-green-700",
};

export default function YearEndPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const perms = user?.permissions ?? [];
  const canCalculate = perms.includes("journal:create");
  const canApprove = perms.includes("payroll:approve");

  const [records, setRecords] = useState<YearEndAdjustment[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState("");
  const [adjustmentYear, setAdjustmentYear] = useState(new Date().getFullYear().toString());
  const [dependentsMap, setDependentsMap] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");

  const fetchRecords = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<{ items: YearEndAdjustment[]; total: number; page: number; page_size: number }>("/year-end/records", {
        company_id: companyId,
        adjustment_year: adjustmentYear,
      });
      setRecords(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const fetchEmployees = async () => {
    if (!companyId) return;
    try {
      const data = await apiGet<{ items: Employee[]; total: number; page: number; page_size: number }>("/payroll/employees", { company_id: companyId });
      setEmployees(data.items);
    } catch {
      // silent
    }
  };

  useEffect(() => {
    if (companyId) {
      fetchRecords();
      fetchEmployees();
    }
  }, [companyId, adjustmentYear]);

  const handleCalculate = async () => {
    if (!companyId) return;
    setCalculating(true);
    setError("");
    try {
      const dependents: Record<string, number> = {};
      for (const [empId, val] of Object.entries(dependentsMap)) {
        if (val && parseInt(val) > 0) {
          dependents[empId] = parseInt(val);
        }
      }
      const data = await apiPost<YearEndAdjustment[]>("/year-end/calculate", {
        company_id: companyId,
        adjustment_year: parseInt(adjustmentYear),
        dependents_override: dependents,
      });
      setRecords(data);
      toast(`${data.length}件の年末調整を計算しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "計算に失敗しました", "error");
    } finally {
      setCalculating(false);
    }
  };

  const handleBatchApprove = async () => {
    if (!companyId) return;
    if (!confirm("全件確定しますか？")) return;
    try {
      const data = await apiPost<YearEndAdjustment[]>(
        `/year-end/records/batch-transition?company_id=${companyId}&adjustment_year=${adjustmentYear}&action=approved`,
        {}
      );
      setRecords(data);
      toast(`${data.length}件を確定しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ステータス更新に失敗しました", "error");
    }
  };

  const handleDownload = async (adjustmentId: string, empName: string) => {
    try {
      const token = localStorage.getItem("token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/year-end/export/${adjustmentId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("取得に失敗しました");
      const text = await res.text();
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `year_end_${empName}_${adjustmentYear}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSVをダウンロードしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ダウンロードに失敗しました", "error");
    }
  };

  const totalGross = records.reduce((s, r) => s + parseFloat(r.total_gross), 0);
  const totalWithholding = records.reduce((s, r) => s + parseFloat(r.withholding_tax_total), 0);
  const totalEstimated = records.reduce((s, r) => s + parseFloat(r.estimated_annual_tax), 0);
  const totalAdjustment = records.reduce((s, r) => s + parseFloat(r.adjustment_amount), 0);

  const filteredRecords = records.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (r.employee_name || r.employee_id).toLowerCase().includes(q);
  });

  const allSameStatus = records.length > 0 && records.every((r) => r.status === records[0].status);
  const currentStatus = records[0]?.status;

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <CalendarClock className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">年末調整</h1>
      </div>

      {!companyId && (
        <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          サイドバーで会社を選択してください。
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="mb-4 flex items-center justify-between rounded-lg border bg-card p-4">
        <div className="flex items-center gap-4">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">対象年</label>
            <input type="number" value={adjustmentYear} onChange={(e) => setAdjustmentYear(e.target.value)} className="w-28 rounded-md border px-3 py-1.5 text-sm" />
          </div>
        </div>
        {canCalculate && (
          <button
            onClick={handleCalculate}
            disabled={calculating || !companyId}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            <Calculator className="h-4 w-4" />
            {calculating ? "計算中..." : "年末調整計算実行"}
          </button>
        )}
      </div>

      {canCalculate && employees.length > 0 && (
        <div className="mb-4 rounded-lg border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold">扶養親族の数（個別設定）</h3>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {employees.map((e) => (
              <div key={e.employee_id} className="flex items-center gap-2">
                <label className="whitespace-nowrap text-xs text-muted-foreground">{e.employee_name}</label>
                <input
                  type="number"
                  min="0"
                  placeholder="0"
                  value={dependentsMap[e.employee_id] || ""}
                  onChange={(ev) => setDependentsMap({ ...dependentsMap, [e.employee_id]: ev.target.value })}
                  className="w-16 rounded-md border px-2 py-1 text-sm"
                />
                <span className="text-xs text-muted-foreground">人</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">未設定の場合は0人（扶養控除なし）で計算されます</p>
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={5} columns={7} />
      ) : records.length > 0 ? (
        <>
          <div className="mb-3 flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="従業員名で検索..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-48 rounded-md border py-1.5 pl-8 pr-3 text-sm"
              />
            </div>
            <span className="text-xs text-muted-foreground">{filteredRecords.length}/{records.length}件</span>
          </div>
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">従業員</th>
                  <th className="px-4 py-3 text-right font-medium">年間給与</th>
                  <th className="px-4 py-3 text-right font-medium">年間賞与</th>
                  <th className="px-4 py-3 text-right font-medium">課税対象額</th>
                  <th className="px-4 py-3 text-right font-medium">源泉徴収額</th>
                  <th className="px-4 py-3 text-right font-medium">推定年税</th>
                  <th className="px-4 py-3 text-right font-medium">調整額</th>
                  <th className="px-4 py-3 text-center font-medium">扶養</th>
                  <th className="px-4 py-3 text-center font-medium">ステータス</th>
                  <th className="px-4 py-3 text-center font-medium">CSV</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map((r) => (
                  <tr key={r.adjustment_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(r.annual_salary).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(r.annual_bonus).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-medium">¥{parseInt(r.total_gross).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-red-600">¥{parseInt(r.withholding_tax_total).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-red-600">¥{parseInt(r.estimated_annual_tax).toLocaleString()}</td>
                    <td className={`px-4 py-3 text-right font-bold ${parseFloat(r.adjustment_amount) >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {parseFloat(r.adjustment_amount) >= 0 ? "+" : ""}¥{parseInt(r.adjustment_amount).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-center">{r.dependents}人</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[r.status] || "bg-gray-100 text-gray-700"}`}>
                        {STATUS_LABELS[r.status] || r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleDownload(r.adjustment_id, r.employee_name || r.employee_id.slice(0, 8))}
                        className="inline-flex items-center justify-center rounded p-1 hover:bg-accent"
                        title="CSV出力"
                      >
                        <Download className="h-4 w-4 text-muted-foreground" />
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
                  <td className="px-4 py-3 text-right text-red-600">¥{totalWithholding.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-red-600">¥{totalEstimated.toLocaleString()}</td>
                  <td className={`px-4 py-3 text-right ${totalAdjustment >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {totalAdjustment >= 0 ? "+" : ""}¥{totalAdjustment.toLocaleString()}
                  </td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-4">
            <div className="rounded-lg border bg-card p-4">
              <p className="text-xs text-muted-foreground">課税対象額合計</p>
              <p className="text-xl font-bold">¥{totalGross.toLocaleString()}</p>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <p className="text-xs text-muted-foreground">源泉徴収額合計</p>
              <p className="text-xl font-bold text-red-600">¥{totalWithholding.toLocaleString()}</p>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <p className="text-xs text-muted-foreground">調整額合計</p>
              <p className={`text-xl font-bold ${totalAdjustment >= 0 ? "text-green-600" : "text-red-600"}`}>
                {totalAdjustment >= 0 ? "+" : ""}¥{totalAdjustment.toLocaleString()}
              </p>
            </div>
          </div>

          {canApprove && allSameStatus && currentStatus === "calculated" && (
            <div className="mt-4 flex items-center gap-2 rounded-lg border bg-card p-4">
              <span className="text-sm font-medium">一括操作:</span>
              <button
                onClick={handleBatchApprove}
                className="flex items-center gap-1 rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
              >
                <CheckCircle className="h-4 w-4" />
                全件確定
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <FileText className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "年末調整データがありません。計算を実行してください。" : "会社を選択してください。"}
          </p>
        </div>
      )}
    </PageLayout>
  );
}
