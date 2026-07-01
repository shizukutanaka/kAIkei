"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { SkeletonTable } from "@/components/skeleton";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import { Receipt, Plus, X, Search, Download, CheckCircle, XCircle, Banknote, Loader2, RefreshCw } from "lucide-react";
import { Pagination } from "@/components/pagination";

interface ExpenseItem {
  item_id: string;
  expense_date: string;
  category: string;
  description: string;
  amount: string;
}

interface ExpenseReport {
  report_id: string;
  employee_id: string;
  company_id: string;
  report_date: string;
  title: string;
  total_amount: string;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  note: string | null;
  employee_name: string | null;
  items: ExpenseItem[];
}

interface Employee {
  employee_id: string;
  employee_name: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  transport: "交通費",
  meal: "会議費",
  accommodation: "宿泊費",
  supplies: "備品消耗品",
  entertainment: "接待交際費",
  other: "その他",
};

const STATUS_LABELS: Record<string, string> = {
  submitted: "申請中",
  approved: "承認済",
  rejected: "差戻し",
  paid: "支払済",
};

const STATUS_COLORS: Record<string, string> = {
  submitted: "bg-yellow-100 text-yellow-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  paid: "bg-blue-100 text-blue-700",
};

const emptyItem = { expense_date: new Date().toISOString().split("T")[0], category: "transport", description: "", amount: "" };

export default function ExpensesPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const perms = user?.permissions ?? [];
  const canCreate = perms.includes("journal:create");
  const canApprove = perms.includes("payroll:approve");

  const [reports, setReports] = useState<ExpenseReport[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 50;
  const [showForm, setShowForm] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<ExpenseReport | null>(null);
  const [formData, setFormData] = useState({
    employee_id: "",
    report_date: new Date().toISOString().split("T")[0],
    title: "",
    note: "",
  });
  const [items, setItems] = useState([{ ...emptyItem }]);

  const isDirty = showForm && (formData.title !== "" || items.some((i) => i.description !== ""));
  useUnsavedChanges(isDirty);

  const fetchReports = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId, page: String(page), page_size: String(pageSize) };
      if (statusFilter) params.status = statusFilter;
      const data = await apiGet<{ items: ExpenseReport[]; total: number; page: number; page_size: number }>("/expenses/reports", params);
      setReports(data.items);
      setTotal(data.total);
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
      fetchReports();
      fetchEmployees();
    }
  }, [companyId, statusFilter, page]);

  const filteredReports = reports.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.title.toLowerCase().includes(q) ||
      (r.employee_name || "").toLowerCase().includes(q)
    );
  });

  const handleAddItem = () => {
    setItems([...items, { ...emptyItem }]);
  };

  const handleRemoveItem = (idx: number) => {
    setItems(items.filter((_, i) => i !== idx));
  };

  const handleItemChange = (idx: number, field: string, value: string) => {
    setItems(items.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  };

  const totalAmount = items.reduce((s, item) => s + (parseFloat(item.amount) || 0), 0);

  const handleSubmit = async () => {
    if (!companyId || !formData.employee_id || !formData.title) {
      toast("従業員とタイトルは必須です", "warning");
      return;
    }
    if (items.length === 0 || items.some((i) => !i.description || !i.amount)) {
      toast("明細の摘要と金額を入力してください", "warning");
      return;
    }
    setSubmitLoading(true);
    try {
      await apiPost("/expenses/reports", {
        company_id: companyId,
        employee_id: formData.employee_id,
        report_date: formData.report_date,
        title: formData.title,
        note: formData.note || null,
        items: items.map((i) => ({
          expense_date: i.expense_date,
          category: i.category,
          description: i.description,
          amount: parseFloat(i.amount),
        })),
      });
      toast("経費精算を提出しました", "success");
      setShowForm(false);
      setFormData({ employee_id: "", report_date: new Date().toISOString().split("T")[0], title: "", note: "" });
      setItems([{ ...emptyItem }]);
      fetchReports();
    } catch (err) {
      toast(err instanceof Error ? err.message : "提出に失敗しました", "error");
    } finally {
      setSubmitLoading(false);
    }
  };

  const [transitionLoading, setTransitionLoading] = useState(false);

  const handleTransition = async (reportId: string, action: "approved" | "rejected" | "paid") => {
    const labels: Record<string, string> = { approved: "承認", rejected: "差戻し", paid: "支払完了" };
    const ok = await confirm({
      title: labels[action],
      message: `経費精算「${selectedReport?.title || ""}」を${labels[action]}しますか？`,
      confirmText: labels[action],
      variant: action === "rejected" ? "danger" : "default",
    });
    if (!ok) return;
    setTransitionLoading(true);
    try {
      const data = await apiPost<ExpenseReport>(
        `/expenses/reports/${reportId}/transition?action=${action}&company_id=${companyId}`,
        {}
      );
      setReports(reports.map((r) => (r.report_id === reportId ? data : r)));
      if (selectedReport?.report_id === reportId) setSelectedReport(data);
      toast(`ステータスを${STATUS_LABELS[action]}に変更しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ステータス変更に失敗しました", "error");
    } finally {
      setTransitionLoading(false);
    }
  };

  const handleDownload = async (reportId: string, title: string) => {
    setDownloadLoading(reportId);
    try {
      const token = localStorage.getItem("token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/expenses/reports/${reportId}/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("取得に失敗しました");
      const text = await res.text();
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `expense_${title}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSVをダウンロードしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ダウンロードに失敗しました", "error");
    } finally {
      setDownloadLoading(null);
    }
  };

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <Receipt className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">経費精算</h1>
      </div>

      {!companyId && (
        <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
          サイドバーで会社を選択してください。
        </div>
      )}

      {error && (
        <div role="alert" className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="タイトル・従業員名で検索..."
              enterKeyHint="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-48 rounded-md border py-1.5 pl-8 pr-7 text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                aria-label="クリア"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-accent"
              >
                <X className="h-3 w-3 text-muted-foreground" />
              </button>
            )}
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border px-2 py-1.5 text-sm"
          >
            <option value="">全ステータス</option>
            <option value="submitted">申請中</option>
            <option value="approved">承認済</option>
            <option value="rejected">差戻し</option>
            <option value="paid">支払済</option>
          </select>
          <span className="text-xs text-muted-foreground">{filteredReports.length}/{reports.length}件</span>
          {filteredReports.length > 0 && (
            <span className="text-xs font-medium text-muted-foreground">
              合計: ¥{filteredReports.reduce((s, r) => s + parseInt(r.total_amount), 0).toLocaleString()}
            </span>
          )}
          <button
            onClick={() => fetchReports()}
            disabled={loading || !companyId}
            className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            更新
          </button>
        </div>
        {canCreate && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            <Plus className="h-4 w-4" />
            新規申請
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">経費精算申請</h2>
            <button onClick={() => setShowForm(false)} className="rounded p-2 hover:bg-accent" aria-label="閉じる">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-3">
            <div>
              <label htmlFor="exp_employee" className="mb-1 block text-sm font-medium">従業員 <span className="text-destructive" aria-hidden="true">*</span></label>
              <select id="exp_employee" value={formData.employee_id} onChange={(e) => setFormData({ ...formData, employee_id: e.target.value })} required aria-required="true" className="w-full rounded-md border px-3 py-2 text-sm">
                <option value="">選択...</option>
                {employees.map((e) => (
                  <option key={e.employee_id} value={e.employee_id}>{e.employee_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="exp_date" className="mb-1 block text-sm font-medium">精算日 <span className="text-destructive" aria-hidden="true">*</span></label>
              <input id="exp_date" type="date" value={formData.report_date} onChange={(e) => setFormData({ ...formData, report_date: e.target.value })} required aria-required="true" className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="exp_title" className="mb-1 block text-sm font-medium">タイトル <span className="text-destructive" aria-hidden="true">*</span></label>
              <input id="exp_title" type="text" value={formData.title} onChange={(e) => setFormData({ ...formData, title: e.target.value })} required aria-required="true" className="w-full rounded-md border px-3 py-2 text-sm" placeholder="例: 6月営業交通費" />
            </div>
          </div>

          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">明細</h3>
              <button onClick={handleAddItem} className="flex items-center gap-1 rounded border px-2 py-1 text-xs hover:bg-accent">
                <Plus className="h-3 w-3" />
                行追加
              </button>
            </div>
            <div className="space-y-2">
              {items.map((item, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2">
                  <input type="date" value={item.expense_date} onChange={(e) => handleItemChange(idx, "expense_date", e.target.value)} className="col-span-2 rounded-md border px-2 py-1.5 text-sm" />
                  <select value={item.category} onChange={(e) => handleItemChange(idx, "category", e.target.value)} className="col-span-2 rounded-md border px-2 py-1.5 text-sm">
                    {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  <input type="text" placeholder="摘要" value={item.description} onChange={(e) => handleItemChange(idx, "description", e.target.value)} className="col-span-5 rounded-md border px-2 py-1.5 text-sm" />
                  <input type="number" placeholder="金額" value={item.amount} onChange={(e) => handleItemChange(idx, "amount", e.target.value)} className="col-span-2 rounded-md border px-2 py-1.5 text-sm text-right" />
                  <button onClick={() => handleRemoveItem(idx)} className="col-span-1 flex items-center justify-center rounded hover:bg-accent">
                    <X className="h-4 w-4 text-muted-foreground" />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-2 flex items-center justify-between border-t pt-2">
              <div>
                <label className="text-sm font-medium">備考</label>
                <input type="text" value={formData.note} onChange={(e) => setFormData({ ...formData, note: e.target.value })} className="ml-2 rounded-md border px-3 py-1 text-sm" placeholder="任意" />
              </div>
              <span className="text-sm font-bold">合計: ¥{totalAmount.toLocaleString()}</span>
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={handleSubmit} disabled={submitLoading} className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {submitLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {submitLoading ? "提出中..." : "提出"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-md border px-4 py-2 text-sm">
              キャンセル
            </button>
          </div>
        </div>
      )}

      {selectedReport && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">精算詳細: {selectedReport.title}</h2>
            <button onClick={() => setSelectedReport(null)} className="rounded p-2 hover:bg-accent" aria-label="閉じる">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">従業員</p>
              <p className="text-sm font-medium">{selectedReport.employee_name}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">精算日</p>
              <p className="text-sm font-medium">{selectedReport.report_date}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">ステータス</p>
              <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[selectedReport.status] || "bg-gray-100 text-gray-700"}`}>
                {STATUS_LABELS[selectedReport.status] || selectedReport.status}
              </span>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">合計金額</p>
              <p className="text-sm font-bold">¥{parseInt(selectedReport.total_amount).toLocaleString()}</p>
            </div>
          </div>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left font-medium">日付</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">カテゴリ</th>
                  <th scope="col" className="px-4 py-3 text-left font-medium">摘要</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">金額</th>
                </tr>
              </thead>
              <tbody>
                {selectedReport.items.map((item) => (
                  <tr key={item.item_id} className="border-t">
                    <td className="px-4 py-3">{item.expense_date}</td>
                    <td className="px-4 py-3">{CATEGORY_LABELS[item.category] || item.category}</td>
                    <td className="px-4 py-3">{item.description}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(item.amount).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 bg-muted/30 font-bold">
                  <td colSpan={3} className="px-4 py-3 text-right">合計</td>
                  <td className="px-4 py-3 text-right">¥{parseInt(selectedReport.total_amount).toLocaleString()}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          {canApprove && selectedReport.status === "submitted" && (
            <div className="mt-4 flex gap-2">
              <button onClick={() => handleTransition(selectedReport.report_id, "approved")} disabled={transitionLoading} className="flex items-center gap-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                承認
              </button>
              <button onClick={() => handleTransition(selectedReport.report_id, "rejected")} disabled={transitionLoading} className="flex items-center gap-1 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                差戻し
              </button>
            </div>
          )}
          {canApprove && selectedReport.status === "approved" && (
            <div className="mt-4 flex gap-2">
              <button onClick={() => handleTransition(selectedReport.report_id, "paid")} disabled={transitionLoading} className="flex items-center gap-1 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Banknote className="h-4 w-4" />}
                支払完了
              </button>
            </div>
          )}
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={5} columns={6} />
      ) : filteredReports.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">経費精算一覧</caption>
            <thead className="bg-muted/50">
              <tr>
                <th scope="col" className="px-4 py-3 text-left font-medium">精算日</th>
                <th scope="col" className="px-4 py-3 text-left font-medium">タイトル</th>
                <th scope="col" className="px-4 py-3 text-left font-medium">従業員</th>
                <th scope="col" className="px-4 py-3 text-right font-medium">合計金額</th>
                <th scope="col" className="px-4 py-3 text-center font-medium">ステータス</th>
                <th scope="col" className="px-4 py-3 text-center font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredReports.map((r) => (
                <tr key={r.report_id} tabIndex={0} className="cursor-pointer border-t hover:bg-muted/30 focus:outline-none focus:ring-2 focus:ring-ring" onClick={() => setSelectedReport(r)} onKeyDown={(e) => { if (e.key === "Enter") setSelectedReport(r); }}>
                  <td className="px-4 py-3">{r.report_date}</td>
                  <td className="px-4 py-3 font-medium">{r.title}</td>
                  <td className="px-4 py-3">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                  <td className="px-4 py-3 text-right font-medium">¥{parseInt(r.total_amount).toLocaleString()}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[r.status] || "bg-gray-100 text-gray-700"}`}>
                      {STATUS_LABELS[r.status] || r.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-center gap-1">
                      <button
                        onClick={() => setSelectedReport(r)}
                        className="rounded px-2 py-1 text-xs hover:bg-accent"
                        title="詳細"
                      >
                        詳細
                      </button>
                      <button
                        onClick={() => handleDownload(r.report_id, r.title)}
                        disabled={downloadLoading === r.report_id}
                        className="inline-flex items-center justify-center rounded p-2 hover:bg-accent disabled:opacity-50"
                        title="CSV出力"
                      >
                        {downloadLoading === r.report_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4 text-muted-foreground" />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 bg-muted/30 font-bold">
                <td colSpan={3} className="px-4 py-3">合計</td>
                <td className="px-4 py-3 text-right">¥{filteredReports.reduce((s, r) => s + parseInt(r.total_amount), 0).toLocaleString()}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <Receipt className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "経費精算データがありません。新規申請を作成してください。" : "会社を選択してください。"}
          </p>
        </div>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
    </PageLayout>
  );
}
