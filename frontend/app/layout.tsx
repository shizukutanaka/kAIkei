import type { Metadata } from "next";
import "./globals.css";
import AuthGuard from "@/components/auth-guard";
import ErrorBoundary from "@/components/error-boundary";
import { CompanyProvider } from "@/lib/company-context";
import { ToastProvider } from "@/components/toast";
import { ConfirmProvider } from "@/components/confirm-dialog";

export const metadata: Metadata = {
  title: {
    default: "kAIkei — 統合バックオフィスプラットフォーム",
    template: "%s | kAIkei",
  },
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
            <ToastProvider>
              <ConfirmProvider>
                <ErrorBoundary>{children}</ErrorBoundary>
              </ConfirmProvider>
            </ToastProvider>
          </CompanyProvider>
        </AuthGuard>
      </body>
    </html>
  );
}
