"use client";

import PageLayout from "@/components/page-layout";
import { Users, Clock } from "lucide-react";

export default function PayrollPage() {
  return (
    <PageLayout>
        <div className="mb-6 flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">給与</h1>
        </div>

        <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-16">
          <Clock className="mb-4 h-12 w-12 text-muted-foreground" />
          <h2 className="mb-2 text-lg font-semibold">準備中</h2>
          <p className="text-center text-sm text-muted-foreground">
            給与計算モジュールは今後のリリースで提供予定です。<br />
            以下の機能を計画しています：
          </p>
          <ul className="mt-4 space-y-1 text-sm text-muted-foreground">
            <li>• 従業員マスタ管理</li>
            <li>• 月次給与計算（基本給・残業代・控除）</li>
            <li>• 源泉所得税・社会保険料計算</li>
            <li>• 給与明細発行</li>
            <li>• 賞与計算</li>
            <li>• 年末調整</li>
          </ul>
        </div>
    </PageLayout>
  );
}
