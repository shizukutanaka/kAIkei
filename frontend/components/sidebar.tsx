"use client";

import { BookOpen, LayoutDashboard, FileText, Settings, Receipt, Users, Building2, Calculator, Sparkles, Globe, FileCheck, List } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-muted/40">
      <div className="flex h-14 items-center gap-2 border-b px-6">
        <Building2 className="h-6 w-6 text-primary" />
        <span className="text-lg font-bold">kAIkei</span>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
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
    </aside>
  );
}
