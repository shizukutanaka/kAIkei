"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/sidebar";

export default function PageLayout({ children, title }: { children: React.ReactNode; title?: string }) {
  const pathname = usePathname();

  useEffect(() => {
    const main = document.querySelector("main");
    if (main) {
      main.focus();
      main.scrollTo(0, 0);
    }
  }, [pathname]);

  useEffect(() => {
    if (title) {
      document.title = `${title} | kAIkei`;
    }
  }, [title]);

  return (
    <div className="flex h-screen pt-14 md:pt-0">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[300] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        メインコンテンツへスキップ
      </a>
      <Sidebar />
      <main id="main-content" aria-label="メインコンテンツ" tabIndex={-1} className="flex-1 overflow-auto p-4 outline-none md:p-8">
        <div className="mx-auto max-w-7xl">
          {children}
        </div>
      </main>
    </div>
  );
}
