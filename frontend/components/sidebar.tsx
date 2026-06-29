"use client";

import { useState } from "react";
import { BookOpen, LayoutDashboard, FileText, Settings, Receipt, Users, Building2, Calculator, Sparkles, Globe, FileCheck, List, Menu, X, Handshake, Gift } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import CompanySelector from "@/components/company-selector";
import { useUser } from "@/lib/use-user";

type NavItem = {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
  permissions?: string[];
};

const navItems: NavItem[] = [
  { label: "ダッシュボード", href: "/dashboard", icon: LayoutDashboard },
  { label: "仕訳入力", href: "/journals/new", icon: Receipt, permissions: ["journal:create"] },
  { label: "仕訳一覧", href: "/journals", icon: List, permissions: ["journal:read"] },
  { label: "AI仕訳推論", href: "/ai-inference", icon: Sparkles, permissions: ["ai:infer", "ai:review"] },
  { label: "承認ワークフロー", href: "/approvals", icon: FileCheck, permissions: ["journal:approve", "journal:post", "journal:create"] },
  { label: "ナレッジ検索", href: "/knowledge", icon: Globe, permissions: ["knowledge:search"] },
  { label: "マスタ", href: "/masters", icon: BookOpen, permissions: ["master:read", "master:create"] },
  { label: "取引先", href: "/partners", icon: Handshake, permissions: ["master:read", "master:create"] },
  { label: "帳票", href: "/reports", icon: FileText, permissions: ["report:read"] },
  { label: "固定資産", href: "/assets", icon: Calculator },
  { label: "給与", href: "/payroll", icon: Users },
  { label: "賞与", href: "/bonus", icon: Gift },
  { label: "設定", href: "/settings", icon: Settings },
];

function hasAnyPermission(userPerms: string[], required?: string[]): boolean {
  if (!required || required.length === 0) return true;
  return required.some((p) => userPerms.includes(p));
}

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { user } = useUser();
  const userPerms = user?.permissions ?? [];

  const visibleItems = navItems.filter((item) => hasAnyPermission(userPerms, item.permissions));

  const navContent = (
    <nav className="flex-1 space-y-1 p-3">
      {visibleItems.map((item) => {
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
