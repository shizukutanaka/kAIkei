"use client";

import { useEffect } from "react";

export default function RootPage() {
  useEffect(() => {
    const token = localStorage.getItem("token");
    window.location.href = token ? "/dashboard" : "/login";
  }, []);

  return (
    <div className="flex h-screen items-center justify-center">
      <p className="text-muted-foreground">リダイレクト中...</p>
    </div>
  );
}
