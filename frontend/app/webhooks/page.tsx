"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useUser } from "@/lib/use-user";
import { SkeletonTable } from "@/components/skeleton";
import { Webhook, Plus, Trash2, Loader2, CheckCircle2, ListTree, RefreshCw } from "lucide-react";

interface Endpoint {
  webhook_endpoint_id: string;
  url: string;
  subscribed_events: string[];
  description: string | null;
  is_active: boolean;
  created_at: string;
}

interface Delivery {
  webhook_delivery_id: string;
  event_type: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  last_status_code: number | null;
  last_error: string | null;
  next_retry_at: string | null;
  delivered_at: string | null;
}

const DELIVERY_STATUS_STYLES: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  delivered: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function WebhooksPage() {
  const { user } = useUser();
  const canManage = user?.permissions.includes("webhook:manage") ?? false;

  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [events, setEvents] = useState("*");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);

  const fetchEndpoints = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiGet<Endpoint[]>("/webhooks");
      setEndpoints(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canManage) fetchEndpoints();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManage]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url || !secret) return;
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const subscribed = events.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
      await apiPost<Endpoint>("/webhooks", {
        url,
        secret,
        subscribed_events: subscribed.length ? subscribed : ["*"],
        description: description || null,
      });
      setNotice("Webhookエンドポイントを登録しました。");
      setUrl(""); setSecret(""); setEvents("*"); setDescription("");
      await fetchEndpoints();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    setError("");
    try {
      await apiDelete(`/webhooks/${id}`);
      if (selectedId === id) { setSelectedId(null); setDeliveries([]); }
      await fetchEndpoints();
    } catch (err) {
      setError(err instanceof Error ? err.message : "削除に失敗しました");
    }
  };

  const viewDeliveries = async (id: string) => {
    setSelectedId(id);
    setDeliveriesLoading(true);
    setError("");
    try {
      const data = await apiGet<Delivery[]>(`/webhooks/${id}/deliveries`, { limit: "50" });
      setDeliveries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "配信履歴の取得に失敗しました");
    } finally {
      setDeliveriesLoading(false);
    }
  };

  const handleReplay = async (deliveryId: string) => {
    setError("");
    try {
      await apiPost(`/webhooks/deliveries/${deliveryId}/replay`, {});
      if (selectedId) await viewDeliveries(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "再送に失敗しました");
    }
  };

  if (!canManage) {
    return (
      <PageLayout title="Webhook管理">
        <p className="text-sm text-muted-foreground">このページを表示する権限がありません（webhook:manage が必要です）。</p>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="Webhook管理">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Webhook className="h-5 w-5" aria-hidden="true" />
          <p className="text-sm">イベント通知先のWebhookエンドポイントを登録し、配信状況を確認します。</p>
        </div>

        {error && <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        {notice && (
          <div role="status" className="flex items-center gap-2 rounded-md border border-green-500/40 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {notice}
          </div>
        )}

        <form onSubmit={handleCreate} aria-labelledby="wh-heading" className="rounded-lg border p-4">
          <h2 id="wh-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold"><Plus className="h-4 w-4" aria-hidden="true" /> エンドポイント登録</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="wh-url" className="mb-1 block text-xs font-medium">通知先URL <span className="text-destructive" aria-hidden="true">*</span></label>
              <input id="wh-url" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/hooks/kaikei" className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="wh-secret" className="mb-1 block text-xs font-medium">署名シークレット <span className="text-destructive" aria-hidden="true">*</span></label>
              <input id="wh-secret" type="text" required minLength={8} value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="8文字以上" className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="wh-events" className="mb-1 block text-xs font-medium">購読イベント（カンマ/改行区切り）</label>
              <input id="wh-events" type="text" value={events} onChange={(e) => setEvents(e.target.value)} placeholder="* または notification.*" className="w-full rounded-md border px-3 py-2 text-sm" aria-describedby="wh-events-hint" />
              <p id="wh-events-hint" className="mt-1 text-xs text-muted-foreground">* は全イベント、notification.* は接頭辞一致。</p>
            </div>
            <div>
              <label htmlFor="wh-desc" className="mb-1 block text-xs font-medium">説明</label>
              <input id="wh-desc" type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="任意" className="w-full rounded-md border px-3 py-2 text-sm" />
            </div>
          </div>
          <button type="submit" disabled={creating || !url || !secret} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
            {creating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} 登録
          </button>
        </form>

        {loading ? (
          <SkeletonTable rows={3} columns={4} />
        ) : endpoints.length === 0 ? (
          <p className="text-sm text-muted-foreground">エンドポイントが登録されていません。</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">登録済みWebhookエンドポイント</caption>
              <thead className="bg-muted/50">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">URL</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">購読イベント</th>
                  <th scope="col" className="px-3 py-2 text-center font-medium">状態</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {endpoints.map((ep) => (
                  <tr key={ep.webhook_endpoint_id} className="border-t">
                    <td className="px-3 py-2 font-mono text-xs">{ep.url}</td>
                    <td className="px-3 py-2">{ep.subscribed_events.join(", ")}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${ep.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>
                        {ep.is_active ? "有効" : "無効"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="inline-flex gap-1">
                        <button type="button" onClick={() => viewDeliveries(ep.webhook_endpoint_id)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground" aria-label={`${ep.url} の配信履歴を表示`}>
                          <ListTree className="h-3 w-3" aria-hidden="true" /> 履歴
                        </button>
                        <button type="button" onClick={() => handleDelete(ep.webhook_endpoint_id)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground" aria-label={`${ep.url} を削除`}>
                          <Trash2 className="h-3 w-3" aria-hidden="true" /> 削除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedId && (
          <section aria-labelledby="deliveries-heading" className="rounded-lg border p-4">
            <h2 id="deliveries-heading" className="mb-3 text-sm font-semibold">配信履歴</h2>
            {deliveriesLoading ? (
              <SkeletonTable rows={3} columns={4} />
            ) : deliveries.length === 0 ? (
              <p className="text-sm text-muted-foreground">配信履歴がありません。</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">選択したエンドポイントの配信履歴</caption>
                  <thead className="bg-muted/50">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-medium">イベント</th>
                      <th scope="col" className="px-3 py-2 text-center font-medium">状態</th>
                      <th scope="col" className="px-3 py-2 text-center font-medium">試行</th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">直近結果</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.map((d) => (
                      <tr key={d.webhook_delivery_id} className="border-t">
                        <td className="px-3 py-2 font-mono text-xs">{d.event_type}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${DELIVERY_STATUS_STYLES[d.status] ?? ""}`}>{d.status}</span>
                        </td>
                        <td className="px-3 py-2 text-center">{d.attempt_count}/{d.max_attempts}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">{d.last_error ?? (d.last_status_code ? `HTTP ${d.last_status_code}` : "-")}</td>
                        <td className="px-3 py-2 text-right">
                          {d.status === "failed" && (
                            <button
                              type="button"
                              onClick={() => handleReplay(d.webhook_delivery_id)}
                              className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                              aria-label={`配信 ${d.event_type} を再送`}
                            >
                              <RefreshCw className="h-3 w-3" aria-hidden="true" /> 再送
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>
    </PageLayout>
  );
}
