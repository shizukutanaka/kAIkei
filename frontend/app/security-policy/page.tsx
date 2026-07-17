"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPut } from "@/lib/api";
import { useUser } from "@/lib/use-user";
import { SkeletonCard } from "@/components/skeleton";
import { ShieldCheck, Save, Loader2, CheckCircle2 } from "lucide-react";

interface SecurityPolicy {
  tenant_security_policy_id: string;
  tenant_id: string;
  require_mfa: boolean;
  allowed_ip_cidrs: string[];
  session_timeout_minutes: number;
  password_min_length: number;
  max_failed_attempts: number;
}

export default function SecurityPolicyPage() {
  const { user } = useUser();
  const canManage = user?.permissions.includes("user:manage") ?? false;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [requireMfa, setRequireMfa] = useState(false);
  const [cidrText, setCidrText] = useState("");
  const [sessionTimeout, setSessionTimeout] = useState(60);
  const [passwordMinLength, setPasswordMinLength] = useState(8);
  const [maxFailedAttempts, setMaxFailedAttempts] = useState(5);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const p = await apiGet<SecurityPolicy>("/security-policy");
      setRequireMfa(p.require_mfa);
      setCidrText((p.allowed_ip_cidrs || []).join("\n"));
      setSessionTimeout(p.session_timeout_minutes);
      setPasswordMinLength(p.password_min_length);
      setMaxFailedAttempts(p.max_failed_attempts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canManage) load();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManage]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const cidrs = cidrText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const updated = await apiPut<SecurityPolicy>("/security-policy", {
        require_mfa: requireMfa,
        allowed_ip_cidrs: cidrs,
        session_timeout_minutes: sessionTimeout,
        password_min_length: passwordMinLength,
        max_failed_attempts: maxFailedAttempts,
      });
      // サーバ側で正規化されたCIDRを反映
      setCidrText((updated.allowed_ip_cidrs || []).join("\n"));
      setNotice("セキュリティポリシーを保存しました。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  if (!canManage) {
    return (
      <PageLayout title="セキュリティポリシー">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（user:manage が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="セキュリティポリシー">
      <div className="max-w-2xl space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">テナント単位の認証・アクセス制御ポリシーを設定します。</p>
        </div>

        {error && <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        {loading ? (
          <SkeletonCard />
        ) : (
          <form onSubmit={handleSave} className="space-y-5 rounded-lg border p-5">
            <div className="flex items-center gap-3">
              <input
                id="require-mfa"
                type="checkbox"
                checked={requireMfa}
                onChange={(e) => setRequireMfa(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              <label htmlFor="require-mfa" className="text-sm font-medium">多要素認証（MFA）を必須にする</label>
            </div>

            <div>
              <label htmlFor="cidrs" className="mb-1 block text-sm font-medium">許可IP帯域（CIDR、1行に1つ）</label>
              <textarea
                id="cidrs"
                value={cidrText}
                onChange={(e) => setCidrText(e.target.value)}
                rows={4}
                placeholder={"例:\n203.0.113.0/24\n198.51.100.10/32"}
                className="w-full rounded-md border px-3 py-2 font-mono text-sm"
                aria-describedby="cidrs-hint"
              />
              <p id="cidrs-hint" className="mt-1 text-xs text-muted-foreground">空欄の場合はIP制限なし。無効なCIDRは保存時に除外されます。</p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="session-timeout" className="mb-1 block text-sm font-medium">セッション有効(分)</label>
                <input id="session-timeout" type="number" min={5} max={1440} value={sessionTimeout} onChange={(e) => setSessionTimeout(Number(e.target.value))} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="password-min" className="mb-1 block text-sm font-medium">最小パスワード長</label>
                <input id="password-min" type="number" min={8} max={128} value={passwordMinLength} onChange={(e) => setPasswordMinLength(Number(e.target.value))} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="max-failed" className="mb-1 block text-sm font-medium">ロックアウト失敗回数</label>
                <input id="max-failed" type="number" min={1} max={20} value={maxFailedAttempts} onChange={(e) => setMaxFailedAttempts(Number(e.target.value))} className="w-full rounded-md border px-3 py-2 text-sm" />
              </div>
            </div>

            <button type="submit" disabled={saving} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              保存
            </button>
          </form>
        )}
      </div>
    </PageLayout>
  );
}
