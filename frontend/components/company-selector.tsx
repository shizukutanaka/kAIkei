"use client";

import { useCompany } from "@/lib/company-context";
import { Building2 } from "lucide-react";

export default function CompanySelector() {
  const { companyId, setCompanyId } = useCompany();

  return (
    <div className="border-t p-3">
      <label className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Building2 className="h-3 w-3" />
        会社ID
      </label>
      <input
        type="text"
        value={companyId}
        onChange={(e) => setCompanyId(e.target.value)}
        placeholder="UUIDを入力"
        className="w-full rounded-md border px-2 py-1.5 text-xs"
      />
    </div>
  );
}
