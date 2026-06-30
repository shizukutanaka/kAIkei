"use client";

import { useState, useEffect, useRef } from "react";
import { Bell, Check, CheckCheck, X, BellOff, Loader2 } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import Link from "next/link";

interface Notification {
  notification_id: string;
  category: string;
  priority: string;
  title: string;
  body: string;
  action_url: string | null;
  is_read: boolean;
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

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = async () => {
    try {
      const data = await apiGet<{ unread_count: number }>("/notifications/unread-count");
      setUnreadCount(data.unread_count);
    } catch {
      // silent
    }
  };

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const data = await apiGet<NotificationList>("/notifications", {
        page: "1",
        page_size: "10",
      });
      setNotifications(data.items);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (open) fetchNotifications();
  }, [open]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeydown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeydown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeydown);
    };
  }, []);

  const handleMarkRead = async (id: string) => {
    try {
      await apiPost(`/notifications/mark-read/${id}`, {});
      setNotifications((prev) =>
        prev.map((n) => (n.notification_id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // silent
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await apiPost("/notifications/mark-all-read", {});
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // silent
    }
  };

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "たった今";
    if (mins < 60) return `${mins}分前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}時間前`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}日前`;
    return d.toLocaleDateString("ja-JP");
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(!open)}
        className="relative rounded-md p-2 hover:bg-accent"
        aria-label="通知"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border bg-popover shadow-lg md:w-96">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h3 className="text-sm font-semibold">通知</h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                  全て既読
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="rounded p-1 hover:bg-accent"
                aria-label="閉じる"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                読み込み中...
              </div>
            ) : notifications.length > 0 ? (
              notifications.map((n) => (
                <div
                  key={n.notification_id}
                  className={`border-b border-l-2 px-4 py-3 hover:bg-muted/50 ${
                    n.is_read ? "opacity-60" : ""
                  } ${PRIORITY_COLORS[n.priority] || "border-l-blue-400"}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                          {CATEGORY_LABELS[n.category] || n.category}
                        </span>
                        {!n.is_read && (
                          <span className="h-2 w-2 rounded-full bg-blue-500" />
                        )}
                        <span className="text-[10px] text-muted-foreground">
                          {formatTime(n.created_at)}
                        </span>
                      </div>
                      <p className="text-sm font-medium">{n.title}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{n.body}</p>
                      {n.action_url && (
                        <Link
                          href={n.action_url}
                          onClick={() => setOpen(false)}
                          className="mt-1 inline-block text-xs text-primary hover:underline"
                        >
                          詳細を見る →
                        </Link>
                      )}
                    </div>
                    {!n.is_read && (
                      <button
                        onClick={() => handleMarkRead(n.notification_id)}
                        className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                        aria-label="既読にする"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center p-8">
                <BellOff className="mb-2 h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">通知はありません</p>
              </div>
            )}
          </div>

          {notifications.length > 0 && (
            <div className="border-t px-4 py-2 text-center">
              <Link
                href="/notifications"
                onClick={() => setOpen(false)}
                className="text-xs text-primary hover:underline"
              >
                すべての通知を見る →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
