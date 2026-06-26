import Sidebar from "@/components/sidebar";

export default function DashboardPage() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <h1 className="mb-6 text-2xl font-bold">ダッシュボード</h1>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border bg-card p-6">
            <p className="text-sm text-muted-foreground">当月仕訳数</p>
            <p className="mt-2 text-3xl font-bold">0</p>
          </div>
          <div className="rounded-lg border bg-card p-6">
            <p className="text-sm text-muted-foreground">未承認</p>
            <p className="mt-2 text-3xl font-bold">0</p>
          </div>
          <div className="rounded-lg border bg-card p-6">
            <p className="text-sm text-muted-foreground">AI推論</p>
            <p className="mt-2 text-3xl font-bold">0</p>
          </div>
          <div className="rounded-lg border bg-card p-6">
            <p className="text-sm text-muted-foreground">アラート</p>
            <p className="mt-2 text-3xl font-bold">0</p>
          </div>
        </div>
      </main>
    </div>
  );
}
