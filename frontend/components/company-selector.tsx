"use client";

import { useEffect, useState } from "react";
import { useCompany } from "@/lib/company-context";
import { apiGet, apiPost } from "@/lib/api";
import { Building2, ChevronDown, Loader2, Plus } from "lucide-react";

interface CompanyOption {
  company_id: string;
  company_name: string;
  company_code: string;
}

export default function CompanySelector() {
  const { companyId, setCompanyId } = useCompany();
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [error, setError] = useState("");

  // 会社が1社も無いと、company_id を要求する全ての画面が使えない。
  // ここで作れるようにしておかないと、登録直後の利用者が詰まる。
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newCode.trim()) return;
    setCreating(true);
    setError("");
    try {
      const created = await apiPost<CompanyOption>("/companies", {
        company_name: newName.trim(),
        company_code: newCode.trim(),
      });
      setCompanies((prev) => [...prev, created]);
      setCompanyId(created.company_id);
      setNewName("");
      setNewCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "会社の作成に失敗しました");
    } finally {
      setCreating(false);
    }
  };

  useEffect(() => {
    const fetchCompanies = async () => {
      try {
        const data = await apiGet<CompanyOption[]>("/companies");
        setCompanies(data);
        if (data.length > 0 && !companyId) {
          const saved = typeof window !== "undefined" ? localStorage.getItem("company_id") || "" : "";
          const matched = saved && data.find((c) => c.company_id === saved);
          if (matched) {
            setCompanyId(matched.company_id);
          } else if (data.length === 1) {
            setCompanyId(data[0].company_id);
          }
        }
      } catch {
        // API not running
      } finally {
        setLoading(false);
      }
    };
    fetchCompanies();
  }, []);

  return (
    <div className="border-t p-3">
      <label className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Building2 className="h-3 w-3" />
        会社
      </label>
      {loading ? (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          読み込み中...
        </div>
      ) : companies.length > 0 ? (
        <div className="relative">
          <select
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
            className="w-full appearance-none rounded-md border bg-background px-2 py-1.5 pr-7 text-xs"
          >
            <option value="">選択してください</option>
            {companies.map((c) => (
              <option key={c.company_id} value={c.company_id}>
                {c.company_name} ({c.company_code})
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        </div>
      ) : (
        <form onSubmit={handleCreate} aria-label="会社の作成" className="space-y-1.5">
          <p className="text-xs text-muted-foreground">
            会社がまだありません。作成すると各機能が使えるようになります。
          </p>
          <input
            type="text"
            aria-label="会社名"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="会社名"
            className="w-full rounded-md border px-2 py-1.5 text-xs"
          />
          <input
            type="text"
            aria-label="会社コード"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
            placeholder="会社コード"
            className="w-full rounded-md border px-2 py-1.5 text-xs"
          />
          {error && (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={creating || !newName.trim() || !newCode.trim()}
            className="inline-flex w-full items-center justify-center gap-1 rounded-md bg-primary px-2 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
          >
            {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
            会社を作成
          </button>
        </form>
      )}
    </div>
  );
}
