"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);
  if (total === 0) return null;

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="mt-4 flex items-center justify-between">
      <p className="text-sm text-muted-foreground">
        {total}件中 {start}-{end}件
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          <ChevronLeft className="h-4 w-4" />
          前へ
        </button>
        <span className="text-sm">{page} / {totalPages || 1}</span>
        <button
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          次へ
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
