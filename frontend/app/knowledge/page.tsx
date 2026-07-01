"use client";

import { useState } from "react";
import PageLayout from "@/components/page-layout";
import { apiPost } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Search, ExternalLink, BookOpen, TrendingUp, Loader2, X } from "lucide-react";
import { SkeletonCard } from "@/components/skeleton";

interface KnowledgeItem {
  title: string;
  url: string;
  source: string;
  summary: string;
  content_preview: string;
  tags: string[];
  author: string;
  published_at: string | null;
  relevance_score: number;
  metadata: Record<string, unknown>;
}

interface SearchResult {
  query: { keywords: string[]; domain: string; language: string };
  total_results: number;
  by_source: Record<string, number>;
  items: KnowledgeItem[];
  errors: Record<string, string> | null;
}

const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  qiita: "Qiita",
  zenn: "Zenn",
  paper: "論文",
};

const SOURCE_COLORS: Record<string, string> = {
  github: "bg-gray-100 text-gray-700",
  qiita: "bg-green-100 text-green-700",
  zenn: "bg-blue-100 text-blue-700",
  paper: "bg-purple-100 text-purple-700",
};

const TOPICS = [
  { topic: "accounting_ai", label: "会計AI", keywords: ["会計", "AI", "仕訳", "自動化"] },
  { topic: "llm_finance", label: "LLM×金融", keywords: ["LLM", "finance", "accounting"] },
  { topic: "japanese_tax", label: "日本の税制", keywords: ["消費税", "軽減税率", "インボイス"] },
  { topic: "erp_modern", label: "モダンERP", keywords: ["ERP", "会計ソフト", "Python"] },
  { topic: "ai_bookkeeping", label: "AI簿記", keywords: ["AI", "簿記", "仕訳推論"] },
];

export default function KnowledgePage() {
  const { toast } = useToast();
  const [keywords, setKeywords] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async (kw?: string[]) => {
    const searchKeywords = kw || keywords.split(/[,\s]+/).filter((k) => k.length > 0);
    if (searchKeywords.length === 0) {
      setError("キーワードを入力してください");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const data = await apiPost<SearchResult>("/knowledge/search", {
        keywords: searchKeywords,
        domain: "accounting",
        language: "ja",
        max_per_source: 5,
      });
      setResults(data);
      toast(`${data.total_results}件の結果を取得しました`, "success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラー");
      toast("検索に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout title="ナレッジ検索">
        <div className="mb-6 flex items-center gap-3">
          <BookOpen className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">ナレッジ検索</h1>
        </div>

        <div className="mb-6 rounded-lg border bg-card p-6">
          <h2 className="mb-4 text-lg font-semibold">検索キーワード</h2>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="会計, AI, 仕訳自動化"
                className="w-full rounded-md border px-3 py-2 pr-8 text-sm"
              />
              {keywords && (
                <button
                  onClick={() => setKeywords("")}
                  aria-label="クリア"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-accent"
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              )}
            </div>
            <button
              onClick={() => handleSearch()}
              disabled={loading}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {loading ? "検索中..." : "検索"}
            </button>
          </div>

          <div className="mt-4">
            <p className="mb-2 text-sm text-muted-foreground">またはトピックから選択:</p>
            <div className="flex flex-wrap gap-2">
              {TOPICS.map((t) => (
                <button
                  key={t.topic}
                  onClick={() => {
                    setKeywords(t.keywords.join(", "));
                    handleSearch(t.keywords);
                  }}
                  className="flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium hover:bg-accent"
                >
                  <TrendingUp className="h-3 w-3" />
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div role="alert" className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading && (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {results && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                {results.total_results}件の結果
              </p>
              <div className="flex gap-2">
                {Object.entries(results.by_source).map(([source, count]) => (
                  <span
                    key={source}
                    className={`rounded px-2 py-1 text-xs font-medium ${SOURCE_COLORS[source] || "bg-gray-100"}`}
                  >
                    {SOURCE_LABELS[source] || source}: {count}
                  </span>
                ))}
              </div>
            </div>

            {results.items.map((item, i) => (
              <div key={i} className="rounded-lg border bg-card p-4">
                <div className="mb-2 flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${SOURCE_COLORS[item.source] || "bg-gray-100"}`}
                      >
                        {SOURCE_LABELS[item.source] || item.source}
                      </span>
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-primary hover:underline"
                      >
                        {item.title}
                      </a>
                      <ExternalLink className="h-3 w-3 text-muted-foreground" />
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    信頼度: {(item.relevance_score * 100).toFixed(0)}%
                  </span>
                </div>

                <p className="mb-2 text-sm text-muted-foreground">{item.summary}</p>
                <p className="mb-2 line-clamp-2 text-xs text-muted-foreground">
                  {item.content_preview}
                </p>

                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  {item.author && <span>著者: {item.author}</span>}
                  {item.published_at && (
                    <span>公開: {new Date(item.published_at).toLocaleDateString("ja-JP")}</span>
                  )}
                  {item.tags.length > 0 && (
                    <div className="flex gap-1">
                      {item.tags.slice(0, 5).map((tag, j) => (
                        <span key={j} className="rounded bg-muted px-1.5 py-0.5">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {results.items.length === 0 && (
              <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-12">
                <Search className="mb-3 h-10 w-10 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  該当する結果が見つかりませんでした。別のキーワードをお試しください。
                </p>
              </div>
            )}
          </div>
        )}
    </PageLayout>
  );
}
