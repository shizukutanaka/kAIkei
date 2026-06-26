"use client";

import { useState } from "react";
import { BookOpen, LayoutDashboard, FileText, Settings, Receipt, Users, Building2, Calculator, Sparkles, Globe, FileCheck, List, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import CompanySelector from "@/components/company-selector";

const navItems = [
  { label: "ダッシュボード", href: "/dashboard", icon: LayoutDashboard },
  { label: "仕訳入力", href: "/journals/new", icon: Receipt },
  { label: "仕訳一覧", href: "/journals", icon: List },
  { label: "AI仕訳推論", href: "/ai-inference", icon: Sparkles },
  { label: "承認ワークフロー", href: "/approvals", icon: FileCheck },
  { label: "ナレッジ検索", href: "/knowledge", icon: Globe },
  { label: "マスタ", href: "/masters", icon: BookOpen },
  { label: "帳票", href: "/reports", icon: FileText },
  { label: "固定資産", href: "/assets", icon: Calculator },
  { label: "給与", href: "/payroll", icon: Users },
  { label: "設定", href: "/settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const navContent = (
    <nav className="flex-1 space-y-1 p-3">
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setOpen(false)}
            className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground ${
              isActive ? "bg-accent text-accent-foreground" : ""
            }`}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <>
      <div className="fixed left-0 right-0 top-0 z-50 flex h-14 items-center justify-between border-b bg-muted/40 px-4 md:hidden">
        <div className="flex items-center gap-2">
          <Building2 className="h-6 w-6 text-primary" />
          <span className="text-lg font-bold">kAIkei</span>
        </div>
        <button
          onClick={() => setOpen(!open)}
          className="rounded-md p-2 hover:bg-accent"
          aria-label="メニュー"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-screen w-60 flex-col border-r bg-muted/40 transition-transform duration-200 md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center gap-2 border-b px-6">
          <Building2 className="h-6 w-6 text-primary" />
          <span className="text-lg font-bold">kAIkei</span>
        </div>
        <CompanySelector />
        {navContent}
      </aside>

      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/20 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}
    </>
  );
}
