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

  const pageNumbers: (number | string)[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pageNumbers.push(i);
  } else {
    pageNumbers.push(1);
    if (page > 3) pageNumbers.push("...");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) {
      pageNumbers.push(i);
    }
    if (page < totalPages - 2) pageNumbers.push("...");
    pageNumbers.push(totalPages);
  }

  return (
    <div className="mt-4 flex items-center justify-between">
      <p className="text-sm text-muted-foreground">
        {total}件中 {start}-{end}件
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          <ChevronLeft className="h-4 w-4" />
          前へ
        </button>
        {pageNumbers.map((p, i) =>
          typeof p === "number" ? (
            <button
              key={i}
              onClick={() => onPageChange(p)}
              className={`min-w-8 rounded-md px-2 py-1.5 text-sm ${
                p === page ? "bg-primary text-primary-foreground" : "border hover:bg-accent"
              }`}
            >
              {p}
            </button>
          ) : (
            <span key={i} className="px-1 text-sm text-muted-foreground">
              {p}
            </span>
          )
        )}
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
