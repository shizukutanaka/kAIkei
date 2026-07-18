import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex items-center justify-center p-12">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <span className="ml-2 text-sm text-muted-foreground">読み込み中...</span>
    </div>
  );
}
