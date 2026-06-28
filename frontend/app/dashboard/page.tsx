"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { useUser } from "@/lib/use-user";
import { Receipt, Clock, Sparkles, AlertCircle, TrendingUp, BookOpen, Calculator, FileCheck } from "lucide-react";

interface JournalList {
  items: Array<{ approval_status: string }>;
  total: number;
  page: number;
  page_size: number;
}

interface DashboardData {
  journalCount: number;
  pendingApprovals: number;
  approvedCount: number;
  draftCount: number;
  accountCount: number;
  assetCount: number;
}

export default function DashboardPage() {
  const { companyId } = useCompany();
  const { user, loading: userLoading } = useUser();
  const [data, setData] = useState<DashboardData>({
    journalCount: 0,
    pendingApprovals: 0,
    approvedCount: 0,
    draftCount: 0,
    accountCount: 0,
    assetCount: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!companyId) {
      setLoading(false);
      return;
    }
    setLoading(true);

    const fetchDashboard = async () => {
      try {
        const [journals, accounts, assets] = await Promise.allSettled([
          apiGet<JournalList>("/journals", { company_id: companyId, page: "1", page_size: "200" }),
          apiGet<unknown[]>("/masters", { company_id: companyId }),
          apiGet<unknown[]>("/fixed-assets", { company_id: companyId }),
        ]);

        const next: DashboardData = {
          journalCount: 0,
          pendingApprovals: 0,
          approvedCount: 0,
          draftCount: 0,
          accountCount: 0,
          assetCount: 0,
        };

        if (journals.status === "fulfilled") {
          next.journalCount = journals.value.total;
          next.pendingApprovals = journals.value.items.filter((j) => j.approval_status === "submitted").length;
          next.approvedCount = journals.value.items.filter((j) => j.approval_status === "approved").length;
          next.draftCount = journals.value.items.filter((j) => j.approval_status === "draft").length;
        }
        if (accounts.status === "fulfilled" && Array.isArray(accounts.value)) {
          next.accountCount = accounts.value.length;
        }
        if (assets.status === "fulfilled" && Array.isArray(assets.value)) {
          next.assetCount = assets.value.length;
        }

        setData(next);
      } catch {
        // API not running
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, [companyId]);

  const cards = [
    { label: "仕訳数", value: data.journalCount, icon: Receipt, color: "text-blue-600" },
    { label: "未承認", value: data.pendingApprovals, icon: Clock, color: "text-yellow-600" },
    { label: "承認済", value: data.approvedCount, icon: FileCheck, color: "text-green-600" },
    { label: "下書き", value: data.draftCount, icon: AlertCircle, color: "text-gray-600" },
    { label: "勘定科目", value: data.accountCount, icon: BookOpen, color: "text-indigo-600" },
    { label: "固定資産", value: data.assetCount, icon: Calculator, color: "text-purple-600" },
  ];

  if (loading || userLoading) {
    return (
      <PageLayout>
        <p className="text-muted-foreground">読み込み中...</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">ダッシュボード</h1>
          {user && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{user.display_name}</span>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                {user.role}
              </span>
            </div>
          )}
        </div>

        {!companyId && (
          <div className="mb-6 rounded-md border border-yellow-500/50 bg-yellow-50 p-4 text-sm text-yellow-700">
            サイドバーで会社IDを入力してください。
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <div key={card.label} className="rounded-lg border bg-card p-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">{card.label}</p>
                  <Icon className={`h-5 w-5 ${card.color}`} />
                </div>
                <p className="mt-2 text-3xl font-bold">{card.value}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <TrendingUp className="h-5 w-5 text-primary" />
              仕訳ステータス
            </h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b pb-3">
                <div className="flex items-center gap-3">
                  <Receipt className="h-4 w-4 text-blue-600" />
                  <span className="text-sm font-medium">総仕訳数</span>
                </div>
                <span className="text-lg font-bold">{data.journalCount}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <div className="flex items-center gap-3">
                  <AlertCircle className="h-4 w-4 text-gray-600" />
                  <span className="text-sm font-medium">下書き</span>
                </div>
                <span className="text-lg font-bold">{data.draftCount}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <div className="flex items-center gap-3">
                  <Clock className="h-4 w-4 text-yellow-600" />
                  <span className="text-sm font-medium">未承認</span>
                </div>
                <span className="text-lg font-bold">{data.pendingApprovals}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileCheck className="h-4 w-4 text-green-600" />
                  <span className="text-sm font-medium">承認済</span>
                </div>
                <span className="text-lg font-bold">{data.approvedCount}</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">システム状態</h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">API サーバー</span>
                <span className="flex items-center gap-1 text-xs text-green-600">
                  <span className="h-2 w-2 rounded-full bg-green-500" />
                  稼働中
                </span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">データベース</span>
                <span className="flex items-center gap-1 text-xs text-green-600">
                  <span className="h-2 w-2 rounded-full bg-green-500" />
                  接続済
                </span>
              </div>
              <div className="flex items-center justify-between border-b pb-3">
                <span className="text-sm">AI プロバイダー</span>
                <span className="flex items-center gap-1 text-xs text-yellow-600">
                  <span className="h-2 w-2 rounded-full bg-yellow-500" />
                  未設定
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">ローカルLLM</span>
                <span className="flex items-center gap-1 text-xs text-gray-500">
                  <span className="h-2 w-2 rounded-full bg-gray-400" />
                  未接続
                </span>
              </div>
            </div>
          </div>
        </div>
    </PageLayout>
  );
}
