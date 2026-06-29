"use client";

import { useEffect } from "react";
import { Loader2 } from "lucide-react";

export default function RootPage() {
  useEffect(() => {
    const token = localStorage.getItem("token");
    window.location.href = token ? "/dashboard" : "/login";
  }, []);

  return (
    <div className="flex h-screen items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}
