import { useQueryClient } from "@tanstack/react-query"
import { CircleStop, RotateCcw } from "lucide-react"
import { toast } from "sonner"

import {
  getListResultOperationsApiResultOperationsGetQueryKey,
  ResultOperationSummaryKind,
  useCancelResultOperationApiResultOperationsJobIdCancelPost,
  useListResultOperationsApiResultOperationsGet,
  useRetryResultOperationApiResultOperationsJobIdRetryPost,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { ApiError } from "@/lib/api-client"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { Button } from "@workspace/ui/components/button"

const params = { limit: 5, offset: 0 }

export function ResultOperationList() {
  const queryClient = useQueryClient()
  const queryKey = getListResultOperationsApiResultOperationsGetQueryKey(params)
  const operations = useListResultOperationsApiResultOperationsGet(params, {
    query: {
      queryKey,
      refetchInterval: document.visibilityState === "hidden" ? false : 1000,
    },
  })
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey })
    void queryClient.invalidateQueries({ queryKey: ["/api/results"] })
  }
  const cancel =
    useCancelResultOperationApiResultOperationsJobIdCancelPost<ApiError>({
      mutation: {
        onSuccess: refresh,
        onError: (error) => toast.error(error.message),
      },
    })
  const retry =
    useRetryResultOperationApiResultOperationsJobIdRetryPost<ApiError>({
      mutation: {
        onSuccess: () => {
          refresh()
          toast.success("任务已重新排队")
        },
        onError: (error) => toast.error(error.message),
      },
    })
  const rows = operations.data?.items ?? []
  if (!rows.length) return null

  return (
    <section className="border-y" aria-label="后台结果任务">
      <div className="divide-y">
        {rows.map((operation) => (
          <div
            className="flex min-w-0 flex-wrap items-center gap-3 px-1 py-2.5"
            key={operation.id}
          >
            <span className="w-24 text-xs font-medium">
              {operation.kind === ResultOperationSummaryKind.resultsplus_check
                ? "Plus 检查"
                : "结果发布"}
            </span>
            <StatusBadge status={operation.status} />
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {operation.processed}/{operation.total}
            </span>
            {operation.failed > 0 && (
              <span className="text-xs text-destructive">
                失败 {operation.failed}
              </span>
            )}
            <span className="ml-auto font-mono text-xs text-muted-foreground">
              {formatCompactBeijingDateTime(operation.created_at)}
            </span>
            {operation.cancelable && (
              <Button
                aria-label="取消后台任务"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate({ jobId: operation.id })}
                size="icon-sm"
                title="取消"
                variant="ghost"
              >
                <CircleStop />
              </Button>
            )}
            {operation.retryable && (
              <Button
                aria-label="重试后台任务"
                disabled={retry.isPending}
                onClick={() => retry.mutate({ jobId: operation.id })}
                size="icon-sm"
                title="重试失败或未处理账号"
                variant="ghost"
              >
                <RotateCcw />
              </Button>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
