"use client";

import PageLayout from "@/components/page-layout";
import { useUser } from "@/lib/use-user";
import { Settings, User, Shield, LogOut } from "lucide-react";
import { SkeletonCard } from "@/components/skeleton";

const ROLE_LABELS: Record<string, string> = {
  admin: "管理者",
  accountant: "経理担当者",
  approver: "承認者",
  viewer: "閲覧者",
};

const PERMISSION_LABELS: Record<string, string> = {
  "journal:create": "仕訳作成",
  "journal:read": "仕訳閲覧",
  "journal:update": "仕訳更新",
  "journal:delete": "仕訳削除",
  "journal:approve": "仕訳承認",
  "journal:post": "仕訳転記",
  "journal:void": "仕訳無効化",
  "master:create": "マスタ作成",
  "master:read": "マスタ閲覧",
  "master:update": "マスタ更新",
  "master:delete": "マスタ削除",
  "ai:infer": "AI推論",
  "ai:review": "AIレビュー",
  "report:read": "帳票閲覧",
  "report:export": "帳票出力",
  "integration:import": "外部連携インポート",
  "integration:config": "外部連携設定",
  "knowledge:search": "ナレッジ検索",
  "user:manage": "ユーザー管理",
};

export default function SettingsPage() {
  const { user, loading } = useUser();

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
  };

  if (loading) {
    return (
      <PageLayout>
        <div className="mb-6 h-8 w-32 animate-pulse rounded bg-muted" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
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
    </PageLayout>
  );
}
