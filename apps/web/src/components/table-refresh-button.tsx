import { RefreshCw } from "lucide-react"

import { Button } from "@workspace/ui/components/button"
import { cn } from "@workspace/ui/lib/utils"

export function TableRefreshButton({
  isRefreshing,
  label = "刷新表格",
  onRefresh,
}: {
  isRefreshing: boolean
  label?: string
  onRefresh: () => void
}) {
  return (
    <Button
      aria-label={label}
      disabled={isRefreshing}
      onClick={onRefresh}
      size="icon-sm"
      title={label}
      variant="outline"
    >
      <RefreshCw className={cn(isRefreshing && "animate-spin")} />
    </Button>
  )
}
