"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { useToast } from "@/components/toast";
import { useConfirm } from "@/components/confirm-dialog";
import { SkeletonTable } from "@/components/skeleton";
import { FileText, Plus, X, Search, Download, Send, CheckCircle, XCircle, Loader2, RefreshCw } from "lucide-react";
import { Pagination } from "@/components/pagination";

interface InvoiceLine {
  line_id: string;
  line_number: number;
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
}

interface Invoice {
  invoice_id: string;
  company_id: string;
  partner_id: string | null;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  total_amount: string;
  status: string;
  note: string | null;
  partner_name: string | null;
  lines: InvoiceLine[];
}

interface Partner {
  partner_id: string;
  partner_name: string;
  partner_code: string;
}

interface InvoiceList {
  items: Invoice[];
  total: number;
  page: number;
  page_size: number;
}

interface PartnerList {
  items: Partner[];
  total: number;
  page: number;
  page_size: number;
}

const STATUS_LABELS: Record<string, string> = {
  draft: "下書き",
  issued: "発行済",
  paid: "入金済",
  cancelled: "キャンセル",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  issued: "bg-blue-100 text-blue-700",
  paid: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700",
};

const emptyLine = { description: "", quantity: "1", unit_price: "" };

export default function InvoicesPage() {
  const { companyId } = useCompany();
  const { user } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const perms = user?.permissions ?? [];
  const canCreate = perms.includes("journal:create");
  const canPost = perms.includes("journal:post");

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 50;
  const [showForm, setShowForm] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  const [formData, setFormData] = useState({
    partner_id: "",
    invoice_number: "",
    invoice_date: new Date().toISOString().split("T")[0],
    due_date: new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0],
    tax_rate: "10",
    note: "",
  });
  const [lines, setLines] = useState([{ ...emptyLine }]);
  const [submitLoading, setSubmitLoading] = useState(false);

  const fetchInvoices = async () => {
    if (!companyId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = { company_id: companyId, page: String(page), page_size: String(pageSize) };
      if (statusFilter) params.status = statusFilter;
      const data = await apiGet<InvoiceList>("/invoices/invoices", params);
      setInvoices(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  const fetchPartners = async () => {
    if (!companyId) return;
    try {
      const data = await apiGet<PartnerList>("/partners", { company_id: companyId });
      setPartners(data.items);
    } catch {
      // silent
    }
  };

  useEffect(() => {
    if (companyId) {
      fetchInvoices();
      fetchPartners();
    }
  }, [companyId, statusFilter, page]);

  const filteredInvoices = invoices.filter((inv) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      inv.invoice_number.toLowerCase().includes(q) ||
      (inv.partner_name || "").toLowerCase().includes(q)
    );
  });

  const handleAddLine = () => setLines([...lines, { ...emptyLine }]);
  const handleRemoveLine = (idx: number) => setLines(lines.filter((_, i) => i !== idx));
  const handleLineChange = (idx: number, field: string, value: string) => {
    setLines(lines.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  };

  const calcSubtotal = () =>
    lines.reduce((s, l) => s + (parseFloat(l.quantity) || 0) * (parseFloat(l.unit_price) || 0), 0);
  const subtotal = calcSubtotal();
  const taxAmount = subtotal * (parseFloat(formData.tax_rate) || 0) / 100;
  const totalAmount = subtotal + taxAmount;

  const handleSubmit = async () => {
    if (!companyId || !formData.invoice_number || !formData.invoice_date || !formData.due_date) {
      toast("請求書番号、請求日、支払期限は必須です", "warning");
      return;
    }
    if (lines.length === 0 || lines.some((l) => !l.description || !l.unit_price)) {
      toast("明細の内容と単価を入力してください", "warning");
      return;
    }
    setSubmitLoading(true);
    try {
      await apiPost("/invoices/invoices", {
        company_id: companyId,
        partner_id: formData.partner_id || null,
        invoice_number: formData.invoice_number,
        invoice_date: formData.invoice_date,
        due_date: formData.due_date,
        tax_rate: parseFloat(formData.tax_rate),
        note: formData.note || null,
        lines: lines.map((l) => ({
          description: l.description,
          quantity: parseFloat(l.quantity) || 1,
          unit_price: parseFloat(l.unit_price),
        })),
      });
      toast("請求書を作成しました", "success");
      setShowForm(false);
      setFormData({
        partner_id: "",
        invoice_number: "",
        invoice_date: new Date().toISOString().split("T")[0],
        due_date: new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0],
        tax_rate: "10",
        note: "",
      });
      setLines([{ ...emptyLine }]);
      fetchInvoices();
    } catch (err) {
      toast(err instanceof Error ? err.message : "作成に失敗しました", "error");
    } finally {
      setSubmitLoading(false);
    }
  };

  const [transitionLoading, setTransitionLoading] = useState(false);

  const handleTransition = async (invoiceId: string, action: "issued" | "paid" | "cancelled") => {
    const labels: Record<string, string> = { issued: "発行", paid: "入金確認", cancelled: "キャンセル" };
    const ok = await confirm({
      title: labels[action],
      message: `請求書 ${selectedInvoice?.invoice_number || ""} を${labels[action]}しますか？`,
      confirmText: labels[action],
      variant: action === "cancelled" ? "danger" : "default",
    });
    if (!ok) return;
    setTransitionLoading(true);
    try {
      const data = await apiPost<Invoice>(
        `/invoices/invoices/${invoiceId}/transition?action=${action}&company_id=${companyId}`,
        {}
      );
      setInvoices(invoices.map((i) => (i.invoice_id === invoiceId ? data : i)));
      if (selectedInvoice?.invoice_id === invoiceId) setSelectedInvoice(data);
      toast(`ステータスを${STATUS_LABELS[action]}に変更しました`, "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ステータス変更に失敗しました", "error");
    } finally {
      setTransitionLoading(false);
    }
  };

  const handleDownload = async (invoiceId: string, number: string) => {
    try {
      const token = localStorage.getItem("token");
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${base}/invoices/invoices/${invoiceId}/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("取得に失敗しました");
      const text = await res.text();
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `invoice_${number}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast("CSVをダウンロードしました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "ダウンロードに失敗しました", "error");
    }
  };

  return (
    <PageLayout>
      <div className="mb-6 flex items-center gap-3">
        <FileText className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">請求書管理</h1>
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

      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="請求書番号・取引先名で検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-56 rounded-md border py-1.5 pl-8 pr-7 text-sm"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
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
            <option value="draft">下書き</option>
            <option value="issued">発行済</option>
            <option value="paid">入金済</option>
            <option value="cancelled">キャンセル</option>
          </select>
          <span className="text-xs text-muted-foreground">{filteredInvoices.length}/{total}件</span>
          {filteredInvoices.length > 0 && (
            <span className="text-xs font-medium text-muted-foreground">
              合計: ¥{filteredInvoices.reduce((s, inv) => s + parseInt(inv.total_amount), 0).toLocaleString()}
            </span>
          )}
          <button
            onClick={() => fetchInvoices()}
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
            新規請求書
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">新規請求書</h2>
            <button onClick={() => setShowForm(false)} className="rounded p-1 hover:bg-accent">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-sm font-medium">請求書番号</label>
              <input type="text" value={formData.invoice_number} onChange={(e) => setFormData({ ...formData, invoice_number: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" placeholder="例: INV-2026-001" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">取引先</label>
              <select value={formData.partner_id} onChange={(e) => setFormData({ ...formData, partner_id: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm">
                <option value="">（なし）</option>
                {partners.map((p) => (
                  <option key={p.partner_id} value={p.partner_id}>{p.partner_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">請求日</label>
              <input type="date" value={formData.invoice_date} onChange={(e) => setFormData({ ...formData, invoice_date: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">支払期限</label>
              <input type="date" value={formData.due_date} onChange={(e) => setFormData({ ...formData, due_date: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">消費税率(%)</label>
              <input type="number" step="0.01" value={formData.tax_rate} onChange={(e) => setFormData({ ...formData, tax_rate: e.target.value })} className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
          </div>

          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">明細</h3>
              <button onClick={handleAddLine} className="flex items-center gap-1 rounded border px-2 py-1 text-xs hover:bg-accent">
                <Plus className="h-3 w-3" />
                行追加
              </button>
            </div>
            <div className="space-y-2">
              {lines.map((line, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2">
                  <input type="text" placeholder="内容" value={line.description} onChange={(e) => handleLineChange(idx, "description", e.target.value)} className="col-span-5 rounded-md border px-2 py-1.5 text-sm" />
                  <input type="number" step="0.001" placeholder="数量" value={line.quantity} onChange={(e) => handleLineChange(idx, "quantity", e.target.value)} className="col-span-2 rounded-md border px-2 py-1.5 text-sm text-right" />
                  <input type="number" placeholder="単価" value={line.unit_price} onChange={(e) => handleLineChange(idx, "unit_price", e.target.value)} className="col-span-3 rounded-md border px-2 py-1.5 text-sm text-right" />
                  <div className="col-span-1 flex items-center text-right text-sm font-medium">
                    ¥{((parseFloat(line.quantity) || 0) * (parseFloat(line.unit_price) || 0)).toLocaleString()}
                  </div>
                  <button onClick={() => handleRemoveLine(idx)} className="col-span-1 flex items-center justify-center rounded hover:bg-accent">
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
              <div className="text-right text-sm">
                <div>小計: ¥{Math.round(subtotal).toLocaleString()}</div>
                <div>消費税: ¥{Math.round(taxAmount).toLocaleString()}</div>
                <div className="font-bold">合計: ¥{Math.round(totalAmount).toLocaleString()}</div>
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={handleSubmit} disabled={submitLoading} className="flex items-center gap-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {submitLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {submitLoading ? "作成中..." : "作成"}
            </button>
            <button onClick={() => setShowForm(false)} className="rounded-md border px-4 py-2 text-sm">
              キャンセル
            </button>
          </div>
        </div>
      )}

      {selectedInvoice && (
        <div className="mb-6 rounded-lg border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">請求書詳細: {selectedInvoice.invoice_number}</h2>
            <button onClick={() => setSelectedInvoice(null)} className="rounded p-1 hover:bg-accent">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">取引先</p>
              <p className="text-sm font-medium">{selectedInvoice.partner_name || "（なし）"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">請求日</p>
              <p className="text-sm font-medium">{selectedInvoice.invoice_date}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">支払期限</p>
              <p className="text-sm font-medium">{selectedInvoice.due_date}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">ステータス</p>
              <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[selectedInvoice.status] || "bg-gray-100 text-gray-700"}`}>
                {STATUS_LABELS[selectedInvoice.status] || selectedInvoice.status}
              </span>
            </div>
          </div>
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-center font-medium">No</th>
                  <th className="px-4 py-3 text-left font-medium">内容</th>
                  <th className="px-4 py-3 text-right font-medium">数量</th>
                  <th className="px-4 py-3 text-right font-medium">単価</th>
                  <th className="px-4 py-3 text-right font-medium">金額</th>
                </tr>
              </thead>
              <tbody>
                {selectedInvoice.lines.map((ln) => (
                  <tr key={ln.line_id} className="border-t">
                    <td className="px-4 py-3 text-center">{ln.line_number}</td>
                    <td className="px-4 py-3">{ln.description}</td>
                    <td className="px-4 py-3 text-right">{parseFloat(ln.quantity).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(ln.unit_price).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">¥{parseInt(ln.line_total).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t bg-muted/30">
                  <td colSpan={4} className="px-4 py-2 text-right text-sm">小計</td>
                  <td className="px-4 py-2 text-right font-medium">¥{parseInt(selectedInvoice.subtotal).toLocaleString()}</td>
                </tr>
                <tr className="border-t">
                  <td colSpan={4} className="px-4 py-2 text-right text-sm">消費税({parseFloat(selectedInvoice.tax_rate)}%)</td>
                  <td className="px-4 py-2 text-right font-medium">¥{parseInt(selectedInvoice.tax_amount).toLocaleString()}</td>
                </tr>
                <tr className="border-t-2 font-bold">
                  <td colSpan={4} className="px-4 py-3 text-right">合計</td>
                  <td className="px-4 py-3 text-right">¥{parseInt(selectedInvoice.total_amount).toLocaleString()}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          {canPost && selectedInvoice.status === "draft" && (
            <div className="mt-4 flex gap-2">
              <button onClick={() => handleTransition(selectedInvoice.invoice_id, "issued")} disabled={transitionLoading} className="flex items-center gap-1 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                発行
              </button>
            </div>
          )}
          {canPost && selectedInvoice.status === "issued" && (
            <div className="mt-4 flex gap-2">
              <button onClick={() => handleTransition(selectedInvoice.invoice_id, "paid")} disabled={transitionLoading} className="flex items-center gap-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                入金確認
              </button>
              <button onClick={() => handleTransition(selectedInvoice.invoice_id, "cancelled")} disabled={transitionLoading} className="flex items-center gap-1 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {transitionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                キャンセル
              </button>
            </div>
          )}
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={5} columns={7} />
      ) : filteredInvoices.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium">請求書番号</th>
                <th className="px-4 py-3 text-left font-medium">請求日</th>
                <th className="px-4 py-3 text-left font-medium">支払期限</th>
                <th className="px-4 py-3 text-left font-medium">取引先</th>
                <th className="px-4 py-3 text-right font-medium">合計金額</th>
                <th className="px-4 py-3 text-center font-medium">ステータス</th>
                <th className="px-4 py-3 text-center font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredInvoices.map((inv) => (
                <tr key={inv.invoice_id} className="cursor-pointer border-t hover:bg-muted/30" onClick={() => setSelectedInvoice(inv)}>
                  <td className="px-4 py-3 font-mono font-medium">{inv.invoice_number}</td>
                  <td className="px-4 py-3">{inv.invoice_date}</td>
                  <td className="px-4 py-3">{inv.due_date}</td>
                  <td className="px-4 py-3">{inv.partner_name || "（なし）"}</td>
                  <td className="px-4 py-3 text-right font-medium">¥{parseInt(inv.total_amount).toLocaleString()}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[inv.status] || "bg-gray-100 text-gray-700"}`}>
                      {STATUS_LABELS[inv.status] || inv.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-center gap-1">
                      <button onClick={() => setSelectedInvoice(inv)} className="rounded px-2 py-1 text-xs hover:bg-accent">詳細</button>
                      <button onClick={() => handleDownload(inv.invoice_id, inv.invoice_number)} className="inline-flex items-center justify-center rounded p-1 hover:bg-accent" title="CSV出力">
                        <Download className="h-4 w-4 text-muted-foreground" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <FileText className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {companyId ? "請求書データがありません。新規作成してください。" : "会社を選択してください。"}
          </p>
        </div>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
    </PageLayout>
  );
}
