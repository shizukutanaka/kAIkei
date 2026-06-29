"use client";

import { useEffect, useState } from "react";
import { useCompany } from "@/lib/company-context";
import { apiGet } from "@/lib/api";
import { Building2, ChevronDown, Loader2 } from "lucide-react";

interface CompanyOption {
  company_id: string;
  company_name: string;
  company_code: string;
}

export default function CompanySelector() {
  const { companyId, setCompanyId } = useCompany();
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [loading, setLoading] = useState(true);

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
        <input
          type="text"
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value)}
          placeholder="UUIDを入力"
          className="w-full rounded-md border px-2 py-1.5 text-xs"
        />
      )}
    </div>
  );
}
