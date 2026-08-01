import { Button } from "@workspace/ui/components/button"
import { RotateCcwIcon } from "lucide-react"
import type { FallbackProps } from "react-error-boundary"

export function AppErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  return (
    <main className="grid min-h-svh place-items-center p-6">
      <section className="w-full max-w-lg border-l-2 border-destructive pl-5">
        <p className="text-sm font-medium text-destructive">页面加载失败</p>
        <p className="mt-2 text-sm text-muted-foreground">
          {error instanceof Error ? error.message : "发生未知错误"}
        </p>
        <Button className="mt-4" variant="outline" onClick={resetErrorBoundary}>
          <RotateCcwIcon />
          重新加载
        </Button>
      </section>
    </main>
  )
}
