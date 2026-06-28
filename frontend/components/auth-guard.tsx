"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (!payload.exp || typeof payload.exp !== "number") return false;
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const [checked, setChecked] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const publicPaths = ["/login", "/"];
    const token = localStorage.getItem("token");

    if (!token || isTokenExpired(token)) {
      localStorage.removeItem("token");
      localStorage.removeItem("refresh_token");
      if (!publicPaths.includes(pathname)) {
        window.location.href = "/login";
        return;
      }
    }

    setChecked(true);
  }, [pathname]);

  if (!checked) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  return <>{children}</>;
}
