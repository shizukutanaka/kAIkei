"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { useUser } from "@/lib/use-user";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Settings, User, Shield, ShieldCheck, LogOut, Bell, Loader2 } from "lucide-react";
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

  // MFA（TOTP）
  const [mfaEnabled, setMfaEnabled] = useState<boolean | null>(null);
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaBusy, setMfaBusy] = useState(false);
  // MFAバックアップコード（平文は再生成直後に一度だけ表示する）
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [backupRemaining, setBackupRemaining] = useState<number | null>(null);

  useEffect(() => {
    const fetchMfa = async () => {
      try {
        const data = await apiGet<{ mfa_enabled: boolean }>("/auth/mfa/status");
        setMfaEnabled(data.mfa_enabled);
        if (data.mfa_enabled) {
          try {
            const s = await apiGet<{ remaining: number }>("/auth/mfa/backup-codes/status");
            setBackupRemaining(s.remaining);
          } catch {
            // 残数が取れなくてもMFA表示は継続
          }
        }
      } catch {
        // API未起動時は非表示のまま
      }
    };
    fetchMfa();
  }, []);

  const handleMfaRegenerateBackupCodes = async () => {
    if (!mfaCode) return;
    setMfaBusy(true);
    try {
      const data = await apiPost<{ codes: string[]; remaining: number }>("/auth/mfa/backup-codes", { code: mfaCode });
      setBackupCodes(data.codes);
      setBackupRemaining(data.remaining);
      setMfaCode("");
      toast("バックアップコードを再生成しました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "バックアップコードの再生成に失敗しました", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const handleMfaSetup = async () => {
    setMfaBusy(true);
    try {
      const data = await apiPost<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup", {});
      setMfaSetup(data);
      setMfaCode("");
    } catch {
      toast("MFAセットアップに失敗しました", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const handleMfaEnable = async () => {
    if (!mfaCode) return;
    setMfaBusy(true);
    try {
      await apiPost<{ mfa_enabled: boolean }>("/auth/mfa/enable", { code: mfaCode });
      setMfaEnabled(true);
      setBackupRemaining(0);  // 有効化直後はバックアップコード未発行
      setMfaSetup(null);
      setMfaCode("");
      toast("MFAを有効化しました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "MFAの有効化に失敗しました", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const handleMfaDisable = async () => {
    if (!mfaCode) return;
    const ok = await confirm({
      title: "MFAの無効化",
      message: "二要素認証を無効化しますか？アカウントの保護レベルが下がります。",
      confirmText: "無効化",
      variant: "danger",
    });
    if (!ok) return;
    setMfaBusy(true);
    try {
      await apiPost<{ mfa_enabled: boolean }>("/auth/mfa/disable", { code: mfaCode });
      setMfaEnabled(false);
      setBackupCodes(null);
      setBackupRemaining(null);
      setMfaCode("");
      toast("MFAを無効化しました", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "MFAの無効化に失敗しました", "error");
    } finally {
      setMfaBusy(false);
    }
  };

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
                  <caption className="sr-only">通知設定</caption>
                  <thead className="bg-muted/50">
                    <tr>
                      <th scope="col" className="px-4 py-3 text-left font-medium">カテゴリ</th>
                      <th scope="col" className="px-4 py-3 text-center font-medium">アプリ内</th>
                      <th scope="col" className="px-4 py-3 text-center font-medium">メール</th>
                      <th scope="col" className="px-4 py-3 text-center font-medium">プッシュ</th>
                      <th scope="col" className="px-4 py-3 text-center font-medium">Webhook</th>
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
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <ShieldCheck className="h-5 w-5 text-primary" />
              二要素認証（MFA）
            </h2>
            {mfaEnabled === null ? (
              <p className="text-sm text-muted-foreground">状態を取得できませんでした。</p>
            ) : mfaEnabled ? (
              <div className="space-y-3">
                <p className="flex items-center gap-2 text-sm text-green-700">
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" /> MFAは有効です。ログイン時に認証アプリのコードが必要になります。
                </p>
                <div className="flex items-end gap-2">
                  <div>
                    <label htmlFor="mfa-disable-code" className="mb-1 block text-xs font-medium">認証コード</label>
                    <input id="mfa-disable-code" type="text" inputMode="numeric" maxLength={8} value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} placeholder="123456" className="w-32 rounded-md border px-3 py-2 text-sm tracking-widest" />
                  </div>
                  <button type="button" onClick={handleMfaRegenerateBackupCodes} disabled={mfaBusy || !mfaCode} className="rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50">
                    バックアップコード再生成
                  </button>
                  <button type="button" onClick={handleMfaDisable} disabled={mfaBusy || !mfaCode} className="rounded-md border border-destructive/50 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50">
                    無効化
                  </button>
                </div>

                {/* バックアップコード（認証アプリ紛失時の復旧手段） */}
                <div className="rounded-md border p-3">
                  <p className="text-xs font-medium">バックアップコード</p>
                  {backupCodes ? (
                    <div className="mt-2 space-y-2">
                      <p className="text-xs text-amber-700">
                        以下のコードは<strong>この画面でのみ</strong>表示されます。安全な場所に保管してください。各コードは1回だけ使用できます。
                      </p>
                      <ul className="grid grid-cols-2 gap-1 font-mono text-sm sm:grid-cols-3">
                        {backupCodes.map((c) => <li key={c} className="rounded bg-muted/50 px-2 py-1">{c}</li>)}
                      </ul>
                      <button type="button" onClick={() => setBackupCodes(null)} className="text-xs text-muted-foreground underline">
                        保管したので閉じる
                      </button>
                    </div>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">
                      未使用の残数: {backupRemaining === null ? "-" : `${backupRemaining}件`}
                      {backupRemaining === 0 && "（認証アプリを紛失するとログインできなくなります。再生成を推奨）"}
                      <br />
                      認証コードを入力して「バックアップコード再生成」を押すと、新しいコードを発行します（既存コードは無効化されます）。
                    </p>
                  )}
                </div>
              </div>
            ) : mfaSetup ? (
              <div className="space-y-3">
                <p className="text-sm">認証アプリ（Google Authenticator等）に以下の秘密鍵を登録し、表示されたコードで有効化してください。</p>
                <div className="rounded-md border bg-muted/50 p-3">
                  <p className="text-xs text-muted-foreground">秘密鍵（手動入力用）</p>
                  <p className="break-all font-mono text-sm">{mfaSetup.secret}</p>
                  <p className="mt-2 text-xs text-muted-foreground">otpauth URI</p>
                  <p className="break-all font-mono text-xs">{mfaSetup.otpauth_uri}</p>
                </div>
                <div className="flex items-end gap-2">
                  <div>
                    <label htmlFor="mfa-enable-code" className="mb-1 block text-xs font-medium">認証コード</label>
                    <input id="mfa-enable-code" type="text" inputMode="numeric" maxLength={8} value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} placeholder="123456" className="w-32 rounded-md border px-3 py-2 text-sm tracking-widest" />
                  </div>
                  <button type="button" onClick={handleMfaEnable} disabled={mfaBusy || !mfaCode} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                    {mfaBusy ? "確認中..." : "有効化"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">MFAは無効です。認証アプリ（TOTP）による二要素認証を設定できます。</p>
                <button type="button" onClick={handleMfaSetup} disabled={mfaBusy} className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                  {mfaBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                  セットアップを開始
                </button>
              </div>
            )}
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
