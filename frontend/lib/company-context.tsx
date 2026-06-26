"use client";

import { createContext, useContext, useEffect, useState } from "react";

interface CompanyContextValue {
  companyId: string;
  setCompanyId: (id: string) => void;
}

const CompanyContext = createContext<CompanyContextValue>({
  companyId: "",
  setCompanyId: () => {},
});

export function CompanyProvider({ children }: { children: React.ReactNode }) {
  const [companyId, setCompanyIdState] = useState("");

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("company_id") || "" : "";
    setCompanyIdState(saved);
  }, []);

  const setCompanyId = (id: string) => {
    setCompanyIdState(id);
    if (typeof window !== "undefined") {
      localStorage.setItem("company_id", id);
    }
  };

  return (
    <CompanyContext.Provider value={{ companyId, setCompanyId }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  return useContext(CompanyContext);
}
