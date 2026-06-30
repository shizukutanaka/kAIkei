"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/sidebar";

export default function PageLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  useEffect(() => {
    const main = document.querySelector("main");
    if (main) {
      main.focus();
      main.scrollTo(0, 0);
    }
  }, [pathname]);

  return (
    <div className="flex h-screen pt-14 md:pt-0">
      <Sidebar />
      <main aria-label="メインコンテンツ" tabIndex={-1} className="flex-1 overflow-auto p-4 outline-none md:p-8">
        <div className="mx-auto max-w-7xl">
          {children}
        </div>
      </main>
    </div>
  );
}
