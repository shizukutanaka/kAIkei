import type { Metadata } from "next";
import "./globals.css";
import AuthGuard from "@/components/auth-guard";

export const metadata: Metadata = {
  title: "kAIkei — 統合バックオフィスプラットフォーム",
  description: "AI-driven integrated ERP system for Japan",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-background antialiased">
        <AuthGuard>{children}</AuthGuard>
      </body>
    </html>
  );
}
