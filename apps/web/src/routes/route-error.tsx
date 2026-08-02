import { isRouteErrorResponse, useRouteError } from "react-router"
import { AlertTriangle } from "lucide-react"

import { Button } from "@workspace/ui/components/button"

export function RouteError() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "页面加载失败"

  return (
    <main className="grid min-h-svh place-items-center p-6">
      <div className="w-full max-w-lg border p-6">
        <AlertTriangle className="mb-4 size-6 text-destructive" />
        <h1 className="text-base font-semibold">无法打开当前页面</h1>
        <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        <Button className="mt-5" onClick={() => window.location.assign("/")}>
          返回工作台
        </Button>
      </div>
    </main>
  )
}
