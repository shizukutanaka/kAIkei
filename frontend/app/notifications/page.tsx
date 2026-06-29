"use client";

import { useState, useEffect } from "react";
import PageLayout from "@/components/page-layout";
import { apiGet, apiPost } from "@/lib/api";
import { Pagination } from "@/components/pagination";
import { Bell, Check, CheckCheck, BellOff } from "lucide-react";

interface Notification {
  notification_id: string;
  category: string;
  priority: string;
  title: string;
  body: string;
  action_url: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

interface NotificationList {
  items: Notification[];
  total: number;
  page: number;
  page_size: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  approval: "承認",
  journal: "仕訳",
  payroll: "給与",
  expense: "経費",
  invoice: "請求書",
  tax: "税務",
  audit: "監査",
  system: "システム",
  ai: "AI",
  period_close: "月次締切",
};

const PRIORITY_COLORS: Record<string, string> = {
  low: "border-l-gray-300",
  normal: "border-l-blue-400",
  high: "border-l-orange-400",
  urgent: "border-l-red-500",
};

const PRIORITY_LABELS: Record<string, string> = {
  low: "低",
  normal: "通常",
  high: "高",
  urgent: "緊急",
};

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const pageSize = 20;

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
      };
      if (unreadOnly) params.unread_only = "true";
      const data = await apiGet<NotificationList>("/notifications", params);
      setNotifications(data.items);
      setTotal(data.total);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, [page, unreadOnly]);

  const handleMarkRead = async (id: string) => {
    try {
      await apiPost(`/notifications/mark-read/${id}`, {});
      setNotifications((prev) =>
        prev.map((n) => (n.notification_id === id ? { ...n, is_read: true } : n))
      );
    } catch {
      // silent
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await apiPost("/notifications/mark-all-read", {});
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch {
      // silent
    }
  };

  const formatTime = (iso: string) => {
    return new Date(iso).toLocaleString("ja-JP");
  };

  return (
    <PageLayout>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">通知</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setUnreadOnly(!unreadOnly); setPage(1); }}
            className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
              unreadOnly ? "bg-primary text-primary-foreground" : "hover:bg-accent"
            }`}
          >
            {unreadOnly ? "未読のみ" : "全て"}
          </button>
          <button
            onClick={handleMarkAllRead}
            className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            <CheckCheck className="h-4 w-4" />
            全て既読
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg border bg-muted/30" />
          ))}
        </div>
      ) : notifications.length > 0 ? (
        <div className="space-y-2">
          {notifications.map((n) => (
            <div
              key={n.notification_id}
              className={`rounded-lg border border-l-4 bg-card p-4 ${
                n.is_read ? "opacity-60" : ""
              } ${PRIORITY_COLORS[n.priority] || "border-l-blue-400"}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="rounded bg-muted px-2 py-0.5 text-xs font-medium">
                      {CATEGORY_LABELS[n.category] || n.category}
                    </span>
                    <span className={`rounded px-2 py-0.5 text-xs ${
                      n.priority === "urgent" ? "bg-red-100 text-red-700" :
                      n.priority === "high" ? "bg-orange-100 text-orange-700" :
                      "bg-muted text-muted-foreground"
                    }`}>
                      {PRIORITY_LABELS[n.priority] || n.priority}
                    </span>
                    {!n.is_read && (
                      <span className="flex items-center gap-1 text-xs text-blue-600">
                        <span className="h-2 w-2 rounded-full bg-blue-500" />
                        未読
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {formatTime(n.created_at)}
                    </span>
                  </div>
                  <p className="font-medium">{n.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{n.body}</p>
                  {n.action_url && (
                    <a
                      href={n.action_url}
                      className="mt-2 inline-block text-sm text-primary hover:underline"
                    >
                      詳細を見る →
                    </a>
                  )}
                </div>
                {!n.is_read && (
                  <button
                    onClick={() => handleMarkRead(n.notification_id)}
                    className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-accent"
                  >
                    <Check className="h-3.5 w-3.5" />
                    既読
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
          <BellOff className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {unreadOnly ? "未読の通知はありません。" : "通知はありません。"}
          </p>
        </div>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
    </PageLayout>
  );
}
