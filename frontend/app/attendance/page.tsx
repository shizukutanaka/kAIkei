"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { SkeletonTable } from "@/components/skeleton";
import { Clock, LogIn, LogOut, Calendar, Search, Plus, X, RefreshCw, Loader2 } from "lucide-react";

interface AttendanceRecord {
  attendance_id: string;
  employee_id: string;
  company_id: string;
  work_date: string;
  clock_in: string | null;
  clock_out: string | null;
  break_minutes: number;
  work_minutes: number;
  overtime_minutes: number;
  leave_type: string;
  note: string | null;
  employee_name: string | null;
}

interface Employee {
  employee_id: string;
  employee_name: string;
}

interface AttendanceSummary {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  days: number;
  total_work_minutes: number;
  total_overtime_minutes: number;
  paid_leave_days: number;
  absent_days: number;
}

const LEAVE_LABELS: Record<string, string> = {
  none: "出勤",
  paid_leave: "有給",
  absent: "欠勤",
  holiday: "休日",
};

const LEAVE_COLORS: Record<string, string> = {
  none: "bg-blue-100 text-blue-700",
  paid_leave: "bg-green-100 text-green-700",
  absent: "bg-red-100 text-red-700",
  holiday: "bg-gray-100 text-gray-700",
};

function formatMinutes(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}h${m > 0 ? `${m}m` : ""}`;
}

function formatTime(dt: string | null): string {
  if (!dt) return "-";
  const d = new Date(dt);
  return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
}

export default function AttendancePage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const perms = user?.permissions ?? [];
  const canCreate = perms.includes("journal:create");

  const [tab, setTab] = useState<"records" | "summary">("records");
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [summary, setSummary] = useState<AttendanceSummary[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [clockLoading, setClockLoading] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const [formData, setFormData] = useState({
    employee_id: "",
    work_date: new Date().toISOString().split("T")[0],
    clock_in: "",
    clock_out: "",
    break_minutes: "60",
    leave_type: "none",
    note: "",
  });

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear().toString());
  const [month, setMonth] = useState((now.getMonth() + 1).toString());

  const fetchEmployees = async () => {
    if (!companyId) return;
    try {
      const data = await apiGet<{ items: Employee[]; total: number; page: number; page_size: number }>("/payroll/employees", { company_id: companyId });
      setEmployees(data.items);
    } catch {
      // silent
    }
  };

  const fetchRecords = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    const startDate = `${year}-${month.padStart(2, "0")}-01`;
    const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate();
    const endDate = `${year}-${month.padStart(2, "0")}-${lastDay.toString().padStart(2, "0")}`;
    try {
      const params: Record<string, string> = {
        company_id: companyId,
        start_date: startDate,
        end_date: endDate,
      };
      if (selectedEmployee) params.employee_id = selectedEmployee;
      const data = await apiGet<{ items: AttendanceRecord[]; total: number; page: number; page_size: number }>("/attendance/records", params);
      setRecords(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<AttendanceSummary[]>("/attendance/summary", {
        company_id: companyId,
        year,
        month,
      });
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) fetchEmployees();
  }, [companyId]);

  useEffect(() => {
    if (companyId) {
      if (tab === "records") fetchRecords();
      else fetchSummary();
    }
  }, [companyId, tab, year, month, selectedEmployee]);

  const handleClockIn = async () => {
    if (!companyId || !selectedEmployee) {
      toast("従業員を選択してください", "warning");
      return;
    }
    setClockLoading(true);
    try {
      await apiPost("/attendance/clock-in", {
        company_id: companyId,
        employee_id: selectedEmployee,
      });
      toast("出勤打刻しました", "success");
      fetchRecords();
    } catch (err) {
      toast(err instanceof Error ? err.message : "打刻に失敗しました", "error");
    } finally {
      setClockLoading(false);
    }
  };

  const handleClockOut = async () => {
    if (!companyId || !selectedEmployee) {
      toast("従業員を選択してください", "warning");
      return;
    }
    setClockLoading(true);
    try {
      await apiPost("/attendance/clock-out", {
        company_id: companyId,
        employee_id: selectedEmployee,
      });
      toast("退勤打刻しました", "success");
      fetchRecords();
    } catch (err) {
      toast(err instanceof Error ? err.message : "打刻に失敗しました", "error");
    } finally {
      setClockLoading(false);
    }
  };

  const handleManualCreate = async () => {
    if (!companyId || !formData.employee_id || !formData.work_date) {
      toast("従業員と日付は必須です", "warning");
      return;
    }
    setFormLoading(true);
    try {
      await apiPost("/attendance/manual", {
        company_id: companyId,
        employee_id: formData.employee_id,
        work_date: formData.work_date,
        clock_in: formData.clock_in ? new Date(`${formData.work_date}T${formData.clock_in}`).toISOString() : null,
        clock_out: formData.clock_out ? new Date(`${formData.work_date}T${formData.clock_out}`).toISOString() : null,
        break_minutes: parseInt(formData.break_minutes) || 60,
        leave_type: formData.leave_type,
        note: formData.note || null,
      });
      toast("勤怠記録を登録しました", "success");
      setShowForm(false);
      fetchRecords();
    } catch (err) {
      toast(err instanceof Error ? err.message : "登録に失敗しました", "error");
    } finally {
      setFormLoading(false);
    }
  };

  const filteredRecords = records.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (r.employee_name || r.employee_id).toLowerCase().includes(q);
  });

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <Clock className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">勤怠管理</h1>
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

      <div className="mb-6 flex gap-2 border-b">
        <button
          onClick={() => setTab("records")}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === "records" ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}
        >
          勤怠記録
        </button>
        <button
          onClick={() => setTab("summary")}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === "summary" ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}
        >
          月次サマリー
        </button>
      </div>

      <div className="mb-4 flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">年</label>
            <input type="number" value={year} onChange={(e) => setYear(e.target.value)} className="w-24 rounded-md border px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">月</label>
            <select value={month} onChange={(e) => setMonth(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>{m}月</option>
              ))}
            </select>
          </div>
          {tab === "records" && (
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">従業員</label>
              <select value={selectedEmployee} onChange={(e) => setSelectedEmployee(e.target.value)} className="rounded-md border px-3 py-1.5 text-sm">
                <option value="">全従業員</option>
                {employees.map((e) => (
                  <option key={e.employee_id} value={e.employee_id}>{e.employee_name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
        {canCreate && tab === "records" && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleClockIn}
              disabled={!companyId || !selectedEmployee || clockLoading}
              className="flex items-center gap-1 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {clockLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
              出勤打刻
            </button>
            <button
              onClick={handleClockOut}
              disabled={!companyId || !selectedEmployee || clockLoading}
              className="flex items-center gap-1 rounded-md bg-orange-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {clockLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              退勤打刻
            </button>
            <button
              onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="h-4 w-4" />
              手動登録
            </button>
            <button
              onClick={() => tab === "records" ? fetchRecords() : fetchSummary()}
              disabled={loading || !companyId}
              className="flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              更新
            </button>
          </div>
        )}
      </div>

      {showForm && tab === "records" && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">手動勤怠登録</h2>
            <button onClick={() => setShowForm(false)} className="rounded p-2 hover:bg-accent" aria-label="閉じる">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-sm font-medium">従業員</label>
              <select value={formData.employee_id} onChange={(e) => setFormData({ ...formData, employee_id: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                <option value="">選択...</option>
                {employees.map((e) => (
                  <option key={e.employee_id} value={e.employee_id}>{e.employee_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">日付</label>
              <input type="date" value={formData.work_date} onChange={(e) => setFormData({ ...formData, work_date: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">出勤時刻</label>
              <input type="time" value={formData.clock_in} onChange={(e) => setFormData({ ...formData, clock_in: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">退勤時刻</label>
              <input type="time" value={formData.clock_out} onChange={(e) => setFormData({ ...formData, clock_out: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">休憩時間（分）</label>
              <input type="number" value={formData.break_minutes} onChange={(e) => setFormData({ ...formData, break_minutes: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">勤怠区分</label>
              <select value={formData.leave_type} onChange={(e) => setFormData({ ...formData, leave_type: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                <option value="none">出勤</option>
                <option value="paid_leave">有給休暇</option>
                <option value="absent">欠勤</option>
                <option value="holiday">休日</option>
              </select>
            </div>
            <div className="col-span-2 md:col-span-3">
              <label className="mb-1 block text-sm font-medium">備考</label>
              <input type="text" value={formData.note} onChange={(e) => setFormData({ ...formData, note: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={handleManualCreate} disabled={formLoading} className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {formLoading ? "登録中..." : "登録"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-md border px-4 py-2 text-sm">
              キャンセル
            </button>
          </div>
        </div>
      )}

      {tab === "records" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="従業員名で検索..."
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
            <span className="text-xs text-muted-foreground">{filteredRecords.length}/{records.length}件</span>
          </div>

          {loading ? (
            <SkeletonTable rows={5} columns={7} />
          ) : filteredRecords.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th scope="col" className="px-4 py-3 text-left font-medium">日付</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">従業員</th>
                    <th scope="col" className="px-4 py-3 text-center font-medium">出勤</th>
                    <th scope="col" className="px-4 py-3 text-center font-medium">退勤</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">勤務時間</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">残業時間</th>
                    <th scope="col" className="px-4 py-3 text-center font-medium">区分</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRecords.map((r) => (
                    <tr key={r.attendance_id} className="border-t hover:bg-muted/30">
                      <td className="px-4 py-3">{r.work_date}</td>
                      <td className="px-4 py-3">{r.employee_name || r.employee_id.slice(0, 8)}</td>
                      <td className="px-4 py-3 text-center">{formatTime(r.clock_in)}</td>
                      <td className="px-4 py-3 text-center">{formatTime(r.clock_out)}</td>
                      <td className="px-4 py-3 text-right">{formatMinutes(r.work_minutes)}</td>
                      <td className={`px-4 py-3 text-right ${r.overtime_minutes > 0 ? "text-orange-600 font-medium" : ""}`}>
                        {r.overtime_minutes > 0 ? formatMinutes(r.overtime_minutes) : "-"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`rounded px-2 py-0.5 text-xs ${LEAVE_COLORS[r.leave_type] || "bg-gray-100 text-gray-700"}`}>
                          {LEAVE_LABELS[r.leave_type] || r.leave_type}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
              <Calendar className="mb-3 h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {companyId ? "勤怠データがありません。打刻または手動登録してください。" : "会社を選択してください。"}
              </p>
            </div>
          )}
        </>
      )}

      {tab === "summary" && (
        <>
          {loading ? (
            <SkeletonTable rows={5} columns={6} />
          ) : summary.length > 0 ? (
            <>
            <p className="mb-2 text-xs text-muted-foreground">{summary.length}人</p>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th scope="col" className="px-4 py-3 text-left font-medium">従業員コード</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">氏名</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">出勤日数</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">総勤務時間</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">総残業時間</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">有給日数</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">欠勤日数</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.map((s) => (
                    <tr key={s.employee_id} className="border-t hover:bg-muted/30">
                      <td className="px-4 py-3 font-mono">{s.employee_code}</td>
                      <td className="px-4 py-3">{s.employee_name}</td>
                      <td className="px-4 py-3 text-right">{s.days}日</td>
                      <td className="px-4 py-3 text-right">{formatMinutes(s.total_work_minutes)}</td>
                      <td className={`px-4 py-3 text-right ${s.total_overtime_minutes > 0 ? "text-orange-600 font-medium" : ""}`}>
                        {s.total_overtime_minutes > 0 ? formatMinutes(s.total_overtime_minutes) : "-"}
                      </td>
                      <td className="px-4 py-3 text-right">{s.paid_leave_days}日</td>
                      <td className={`px-4 py-3 text-right ${s.absent_days > 0 ? "text-red-600" : ""}`}>
                        {s.absent_days > 0 ? `${s.absent_days}日` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 bg-muted/30 font-bold">
                    <td colSpan={2} className="px-4 py-3">合計</td>
                    <td className="px-4 py-3 text-right">{summary.reduce((s, r) => s + r.days, 0)}日</td>
                    <td className="px-4 py-3 text-right">{formatMinutes(summary.reduce((s, r) => s + r.total_work_minutes, 0))}</td>
                    <td className="px-4 py-3 text-right text-orange-600">{(() => { const tot = summary.reduce((s, r) => s + r.total_overtime_minutes, 0); return tot > 0 ? formatMinutes(tot) : "-"; })()}</td>
                    <td className="px-4 py-3 text-right">{summary.reduce((s, r) => s + r.paid_leave_days, 0)}日</td>
                    <td className="px-4 py-3 text-right text-red-600">{(() => { const tot = summary.reduce((s, r) => s + r.absent_days, 0); return tot > 0 ? `${tot}日` : "-"; })()}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
              <Calendar className="mb-3 h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {companyId ? "該当月の勤怠データがありません。" : "会社を選択してください。"}
              </p>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}
