"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { SkeletonTable } from "@/components/skeleton";
import { Gift, Calculator, CheckCircle, XCircle, Banknote, FileText, Download, Search } from "lucide-react";

interface BonusRecord {
  bonus_id: string;
  employee_id: string;
  company_id: string;
  bonus_year: number;
  bonus_term: string;
  bonus_amount: string;
  bonus_base_months: string;
  performance_factor: string;
  income_tax: string;
  social_insurance: string;
  total_deductions: string;
  net_pay: string;
  status: string;
  employee_name: string | null;
}

interface Employee {
  employee_id: string;
  employee_name: string;
  base_salary: string;
}

const BONUS_TERM_LABELS: Record<string, string> = {
  summer: "夏季賞与",
  winter: "冬季賞与",
  yearend: "年末賞与",
  other: "その他",
};

const BONUS_STATUS_LABELS: Record<string, string> = {
  calculated: "計算済",
  approved: "承認済",
  rejected: "差戻し",
  paid: "支払済",
};

const BONUS_STATUS_COLORS: Record<string, string> = {
  calculated: "bg-blue-100 text-blue-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  paid: "bg-gray-100 text-gray-700",
};

export default function BonusPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const perms = user?.permissions ?? [];
  const canCalculate = perms.includes("journal:create");
  const canApprove = perms.includes("payroll:approve");
  const canPost = perms.includes("payroll:post");

  const [bonusRecords, setBonusRecords] = useState<BonusRecord[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState("");
  const [bonusYear, setBonusYear] = useState(new Date().getFullYear().toString());
  const [bonusTerm, setBonusTerm] = useState("summer");
  const [baseMonths, setBaseMonths] = useState("2.0");
  const [perfFactors, setPerfFactors] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");

  const fetchBonusRecords = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<{ items: BonusRecord[]; total: number; page: number; page_size: number }>("/bonus/records", {
        company_id: companyId,
        bonus_year: bonusYear,
        bonus_term: bonusTerm,
      });
      setBonusRecords(data.items);
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
      fetchBonusRecords();
      fetchEmployees();
    }
  }, [companyId, bonusYear, bonusTerm]);

  const handleCalculate = async () => {
    if (!companyId) return;
    setCalculating(true);
    setError("");
    try {
      const factors: Record<string, number> = {};
      for (const [empId, factor] of Object.entries(perfFactors)) {
        if (factor && parseFloat(factor) > 0) {
          factors[empId] = parseFloat(factor);
        }
      }
      const data = await apiPost<BonusRecord[]>("/bonus/calculate", {
        company_id: companyId,
        bonus_year: parseInt(bonusYear),
        bonus_term: bonusTerm,
        bonus_base_months: parseFloat(baseMonths),
        performance_factors: factors,
      });
      setBonusRecords(data);
      toast(`${data.length}件の賞与を計算しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "計算に失敗しました", "error");
    } finally {
      setCalculating(false);
    }
  };

  const handleBatchTransition = async (action: "approved" | "rejected" | "paid") => {
    if (!companyId) return;
    const labels: Record<string, string> = { approved: "承認", rejected: "差戻し", paid: "支払完了" };
    if (!await confirm({ title: "一括処理", message: `全件${labels[action]}しますか？`, confirmText: labels[action] })) return;
    try {
      const data = await apiPost<BonusRecord[]>(
        `/bonus/records/batch-transition?company_id=${companyId}&bonus_year=${bonusYear}&bonus_term=${bonusTerm}&action=${action}`,
        {}
      );
      setBonusRecords(data);
      toast(`${data.length}件を${labels[action]}しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ステータス更新に失敗しました", "error");
    }
  };

  const handleDownload = async (bonusId: string, empName: string) => {
    try {
      const token = localStorage.getItem("token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/bonus/export/${bonusId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("取得に失敗しました");
      const text = await res.text();
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bonus_${empName}_${bonusYear}_${bonusTerm}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSVをダウンロードしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ダウンロードに失敗しました", "error");
    }
  };

  const totalGross = bonusRecords.reduce((s, r) => s + parseFloat(r.bonus_amount), 0);
  const totalDeductions = bonusRecords.reduce((s, r) => s + parseFloat(r.total_deductions), 0);
  const totalNet = bonusRecords.reduce((s, r) => s + parseFloat(r.net_pay), 0);

  const filteredRecords = bonusRecords.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (r.employee_name || r.employee_id).toLowerCase().includes(q);
  });

  const allSameStatus = bonusRecords.length > 0 && bonusRecords.every((r) => r.status === bonusRecords[0].status);
  const currentStatus = bonusRecords[0]?.status;

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <Gift className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">賞与</h1>
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
            <label className="mb-1 block text-xs text-muted-foreground">年</label>
            <input type="number" value={bonusYear} onChange={(e) => setBonusYear(e.target.value)} className="w-24 rounded-md border px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">賞与区分</label>
            <select value={bonusTerm} onChange={(e) => setBonusTerm(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
              {Object.entries(BONUS_TERM_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">基準月数</label>
            <input type="number" step="0.1" value={baseMonths} onChange={(e) => setBaseMonths(e.target.value)} className="w-20 rounded-md border px-3 py-1.5 text-sm" />
          </div>
        </div>
        {canCalculate && (
          <button
            onClick={handleCalculate}
            disabled={calculating || !companyId}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            <Calculator className="h-4 w-4" />
            {calculating ? "計算中..." : "賞与計算実行"}
          </button>
        )}
      </div>

      {canCalculate && employees.length > 0 && (
        <div className="mb-4 rounded-lg border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold">業績係数（個別設定）</h3>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {employees.map((e) => (
              <div key={e.employee_id} className="flex items-center gap-2">
                <label className="whitespace-nowrap text-xs text-muted-foreground">{e.employee_name}</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="1.00"
                  value={perfFactors[e.employee_id] || ""}
                  onChange={(ev) => setPerfFactors({ ...perfFactors, [e.employee_id]: ev.target.value })}
                  className="w-20 rounded-md border px-2 py-1 text-sm"
                />
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">未設定の場合は1.00（標準）で計算されます</p>
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={5} columns={7} />
      ) : bonusRecords.length > 0 ? (
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
            <span className="text-xs text-muted-foreground">{filteredRecords.length}/{bonusRecords.length}件</span>
          </div>
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">従業員</th>
                  <th className="px-4 py-3 text-right font-medium">基準月数</th>
                  <th className="px-4 py-3 text-right font-medium">業績係数</th>
                  <th className="px-4 py-3 text-right font-medium">賞与額</th>
                  <th className="px-4 py-3 text-right font-medium">源泉所得税</th>
                  <th className="px-4 py-3 text-right font-medium">社会保険料</th>
                  <th className="px-4 py-3 text-right font-medium">差引支給額</th>
                  <th className="px-4 py-3 text-center font-medium">ステータス</th>
                  <th className="px-4 py-3 text-center font-medium">CSV</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map((r) => (
                  <tr key={r.bonus_id} className="border-t hover:bg-muted/30">
                    <td className="px-4 py-3">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-right">{parseFloat(r.bonus_base_months).toFixed(1)}ヶ月</td>
                    <td className="px-4 py-3 text-right">{parseFloat(r.performance_factor).toFixed(2)}</td>
                    <td className="px-4 py-3 text-right font-medium">¥{parseInt(r.bonus_amount).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-red-600">¥{parseInt(r.income_tax).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-red-600">¥{parseInt(r.social_insurance).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-bold">¥{parseInt(r.net_pay).toLocaleString()}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`rounded px-2 py-0.5 text-xs ${BONUS_STATUS_COLORS[r.status] || "bg-gray-100 text-gray-700"}`}>
                        {BONUS_STATUS_LABELS[r.status] || r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleDownload(r.bonus_id, r.employee_name || r.employee_id.slice(0, 8))}
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
                  <td colSpan={2} />
                  <td className="px-4 py-3 text-right">¥{totalNet.toLocaleString()}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-4">
            <div className="rounded-lg border bg-card p-4">
              <p className="text-xs text-muted-foreground">賞与総額</p>
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

          {canApprove && allSameStatus && currentStatus && (
            <div className="mt-4 flex items-center gap-2 rounded-lg border bg-card p-4">
              <span className="text-sm font-medium">一括操作:</span>
              {currentStatus === "calculated" && (
                <>
                  <button
                    onClick={() => handleBatchTransition("approved")}
                    className="flex items-center gap-1 rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                  >
                    <CheckCircle className="h-4 w-4" />
                    全件承認
                  </button>
                  <button
                    onClick={() => handleBatchTransition("rejected")}
                    className="flex items-center gap-1 rounded-md border border-red-500 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
                  >
                    <XCircle className="h-4 w-4" />
                    全件差戻し
                  </button>
                </>
              )}
              {currentStatus === "approved" && canPost && (
                <button
                  onClick={() => handleBatchTransition("paid")}
                  className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  <Banknote className="h-4 w-4" />
                  全件支払完了
                </button>
              )}
              {currentStatus === "rejected" && (
                <button
                  onClick={() => handleBatchTransition("approved")}
                  className="flex items-center gap-1 rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                >
                  <CheckCircle className="h-4 w-4" />
                  再承認
                </button>
              )}
              {currentStatus === "paid" && (
                <span className="text-sm text-muted-foreground">支払済みのため操作不可</span>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <FileText className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "賞与データがありません。賞与計算を実行してください。" : "会社を選択してください。"}
          </p>
        </div>
      )}
    </PageLayout>
  );
}
