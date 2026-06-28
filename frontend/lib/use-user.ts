"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export interface UserInfo {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  permissions: string[];
}

export function useUser() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchUser = async () => {
      try {
        const u = await apiGet<UserInfo>("/rbac/me");
        if (!cancelled) setUser(u);
      } catch {
        // API not running
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchUser();
    return () => {
      cancelled = true;
    };
  }, []);

  return { user, loading };
}
