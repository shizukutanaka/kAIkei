"use client";

import Sidebar from "@/components/sidebar";

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen pt-14 md:pt-0">
      <Sidebar />
      <main className="flex-1 overflow-auto p-4 md:p-8">{children}</main>
    </div>
  );
}
