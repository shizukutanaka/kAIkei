"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import { Receipt, Clock, Sparkles, AlertCircle, TrendingUp } from "lucide-react";

interface DashboardData {
  user: { email: string; display_name: string; role: string; permissions: string[] } | null;
  journalCount: number;
  pendingApprovals: number;
  aiInferences: number;
  alerts: number;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData>({
    user: null,
    journalCount: 0,
    pendingApprovals: 0,
    aiInferences: 0,
    alerts: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const fetchUserData = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/v1/rbac/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const user = await response.json();
          setData((prev) => ({ ...prev, user }));
        } else if (response.status === 401) {
          localStorage.removeItem("token");
          window.location.href = "/login";
        }
      } catch {
        // API not running yet — show dashboard with zeros
      } finally {
        setLoading(false);
      }
    };

    fetchUserData();
  }, []);

  const cards = [
    { label: "当月仕訳数", value: data.journalCount, icon: Receipt, color: "text-blue-600" },
    { label: "未承認", value: data.pendingApprovals, icon: Clock, color: "text-yellow-600" },
    { label: "AI推論", value: data.aiInferences, icon: Sparkles, color: "text-purple-600" },
    { label: "アラート", value: data.alerts, icon: AlertCircle, color: "text-red-600" },
  ];

  if (loading) {
    return (
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 overflow-auto p-8">
          <p className="text-muted-foreground">読み込み中...</p>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">ダッシュボード</h1>
          {data.user && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{data.user.display_name}</span>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                {data.user.role}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
              最近の活動
            </h2>
            <div className="space-y-3">
              <div className="flex items-center gap-3 border-b pb-3">
                <Receipt className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1">
                  <p className="text-sm font-medium">仕訳入力</p>
                  <p className="text-xs text-muted-foreground">仕訳の作成・編集</p>
                </div>
              </div>
              <div className="flex items-center gap-3 border-b pb-3">
                <Sparkles className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1">
                  <p className="text-sm font-medium">AI仕訳推論</p>
                  <p className="text-xs text-muted-foreground">AIによる自動仕訳提案</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1">
                  <p className="text-sm font-medium">承認待ち</p>
                  <p className="text-xs text-muted-foreground">承認ワークフロー</p>
                </div>
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
      </main>
    </div>
  );
}
