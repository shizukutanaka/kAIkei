"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/sidebar";
import { Settings, User, Shield, LogOut } from "lucide-react";

interface UserInfo {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  permissions: string[];
}

const ROLE_LABELS: Record<string, string> = {
  admin: "管理者",
  accountant: "経理担当者",
  approver: "承認者",
  viewer: "閲覧者",
};

const PERMISSION_LABELS: Record<string, string> = {
  journal_create: "仕訳作成",
  journal_read: "仕訳閲覧",
  journal_approve: "仕訳承認",
  journal_post: "仕訳転記",
  master_create: "マスタ作成",
  master_read: "マスタ閲覧",
  report_read: "帳票閲覧",
  ai_inference: "AI推論",
  knowledge_search: "ナレッジ検索",
  integration_use: "外部連携",
  user_manage: "ユーザー管理",
};

export default function SettingsPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const fetchUser = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/v1/rbac/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          setUser(await response.json());
        } else if (response.status === 401) {
          localStorage.removeItem("token");
          window.location.href = "/login";
        }
      } catch {
        // API not running
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
  };

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
        <div className="mb-6 flex items-center gap-3">
          <Settings className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">設定</h1>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <User className="h-5 w-5 text-primary" />
              ユーザー情報
            </h2>
            {user ? (
              <div className="space-y-3">
                <div className="flex justify-between border-b pb-2">
                  <span className="text-sm text-muted-foreground">ユーザーID</span>
                  <span className="font-mono text-sm">{user.user_id}</span>
                </div>
                <div className="flex justify-between border-b pb-2">
                  <span className="text-sm text-muted-foreground">メールアドレス</span>
                  <span className="text-sm">{user.email}</span>
                </div>
                <div className="flex justify-between border-b pb-2">
                  <span className="text-sm text-muted-foreground">表示名</span>
                  <span className="text-sm">{user.display_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">ロール</span>
                  <span className="rounded-full bg-primary/10 px-3 py-0.5 text-xs font-medium text-primary">
                    {ROLE_LABELS[user.role] || user.role}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">ユーザー情報を取得できませんでした</p>
            )}
          </div>

          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <Shield className="h-5 w-5 text-primary" />
              権限一覧
            </h2>
            {user && user.permissions.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {user.permissions.map((perm) => (
                  <span
                    key={perm}
                    className="rounded-md border bg-muted/50 px-3 py-1 text-xs"
                  >
                    {PERMISSION_LABELS[perm] || perm}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">権限がありません</p>
            )}
          </div>

          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">システム情報</h2>
            <div className="space-y-3">
              <div className="flex justify-between border-b pb-2">
                <span className="text-sm text-muted-foreground">アプリケーション</span>
                <span className="text-sm">kAIkei</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-sm text-muted-foreground">API エンドポイント</span>
                <span className="font-mono text-sm">localhost:8000</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">フロントエンド</span>
                <span className="font-mono text-sm">localhost:3000</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">アカウント操作</h2>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-md border border-destructive/50 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/10"
            >
              <LogOut className="h-4 w-4" />
              ログアウト
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
