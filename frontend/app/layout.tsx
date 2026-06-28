import type { Metadata } from "next";
import "./globals.css";
import AuthGuard from "@/components/auth-guard";
import { CompanyProvider } from "@/lib/company-context";
import { ToastProvider } from "@/components/toast";

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
        <AuthGuard>
          <CompanyProvider>
            <ToastProvider>{children}</ToastProvider>
          </CompanyProvider>
        </AuthGuard>
      </body>
    </html>
  );
}
