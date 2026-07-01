"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { useUser } from "@/lib/use-user";
import { apiGet, apiPut } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Settings, User, Shield, LogOut, Bell, Loader2 } from "lucide-react";
import { SkeletonCard } from "@/components/skeleton";
import { useConfirm } from "@/components/confirm-dialog";

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

const CATEGORY_LABELS: Record<string, string> = {
  approval: "承認",
  journal: "仕訳",
  payroll: "給与・賞与",
  expense: "経費精算",
  invoice: "請求書",
  tax: "税務",
  audit: "監査",
  system: "システム",
  ai: "AI",
  period_close: "期首期末",
};

interface NotificationPreference {
  preference_id: string;
  user_id: string;
  category: string;
  channel_inapp: boolean;
  channel_email: boolean;
  channel_push: boolean;
  channel_webhook: boolean;
}

export default function SettingsPage() {
  const { user, loading } = useUser();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const [prefs, setPrefs] = useState<NotificationPreference[]>([]);
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [updatingCat, setUpdatingCat] = useState<string | null>(null);
  const [logoutLoading, setLogoutLoading] = useState(false);

  useEffect(() => {
    const fetchPrefs = async () => {
      setPrefsLoading(true);
      try {
        const data = await apiGet<NotificationPreference[]>("/notifications/preferences");
        setPrefs(data);
      } catch {
        // API not running or no prefs yet
      } finally {
        setPrefsLoading(false);
      }
    };
    fetchPrefs();
  }, []);

  const handleToggleChannel = async (category: string, channel: "channel_inapp" | "channel_email" | "channel_push" | "channel_webhook") => {
    const current = prefs.find((p) => p.category === category);
    const newValue = current ? !current[channel] : true;
    setUpdatingCat(category);
    try {
      const updated = await apiPut<NotificationPreference>(
        `/notifications/preferences/${category}`,
        { [channel]: newValue }
      );
      setPrefs((prev) => {
        const idx = prev.findIndex((p) => p.category === category);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = updated;
          return next;
        }
        return [...prev, updated];
      });
    } catch {
      toast("通知設定の更新に失敗しました", "error");
    } finally {
      setUpdatingCat(null);
    }
  };

  const handleLogout = async () => {
    const ok = await confirm({
      title: "ログアウト",
      message: "ログアウトしますか？",
      confirmText: "ログアウト",
      variant: "danger",
    });
    if (!ok) return;
    setLogoutLoading(true);
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
  };

  if (loading) {
    return (
      <PageLayout title="設定">
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

          <div className="rounded-lg border bg-card p-6 lg:col-span-2">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <Bell className="h-5 w-5 text-primary" />
              通知設定
            </h2>
            {prefsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                読み込み中...
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">カテゴリ</th>
                      <th className="px-4 py-3 text-center font-medium">アプリ内</th>
                      <th className="px-4 py-3 text-center font-medium">メール</th>
                      <th className="px-4 py-3 text-center font-medium">プッシュ</th>
                      <th className="px-4 py-3 text-center font-medium">Webhook</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(CATEGORY_LABELS).map(([cat, label]) => {
                      const pref = prefs.find((p) => p.category === cat);
                      const isUpdating = updatingCat === cat;
                      return (
                        <tr key={cat} className="border-t hover:bg-muted/30">
                          <td className="px-4 py-3 font-medium">{label}</td>
                          {(["channel_inapp", "channel_email", "channel_push", "channel_webhook"] as const).map((ch) => (
                            <td key={ch} className="px-4 py-3 text-center">
                              <button
                                onClick={() => handleToggleChannel(cat, ch)}
                                disabled={isUpdating}
                                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
                                  pref?.[ch] ? "bg-primary" : "bg-muted"
                                }`}
                              >
                                <span
                                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                                    pref?.[ch] ? "translate-x-4" : "translate-x-1"
                                  }`}
                                />
                              </button>
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              各カテゴリの通知チャネルを個別に有効/無効できます。
            </p>
          </div>

          <div className="rounded-lg border bg-card p-6">
            <h2 className="mb-4 text-lg font-semibold">アカウント操作</h2>
            <button
              onClick={handleLogout}
              disabled={logoutLoading}
              className="flex items-center gap-2 rounded-md border border-destructive/50 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
            >
              {logoutLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              {logoutLoading ? "ログアウト中..." : "ログアウト"}
            </button>
          </div>
        </div>
    </PageLayout>
  );
}
