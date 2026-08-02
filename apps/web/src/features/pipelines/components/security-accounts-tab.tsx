import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Clipboard, RefreshCw, ShieldCheck, X } from "lucide-react"
import { toast } from "sonner"

import {
  type PipelineItemListResponse,
  type PipelineRunDetail,
  type ResultOperationSummary,
} from "@/api/generated"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import {
  PlusStateBadge,
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import { usePipelineRunRouteState } from "@/features/pipelines/hooks/use-pipeline-run-route-state"
import { TASK_STATUS_LABELS } from "@/features/pipelines/lib/pipeline-state"
import { runResultOperation } from "@/features/results/lib/result-operations"
import { ApiError, apiRequest } from "@/lib/api-client"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@workspace/ui/components/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"
import { TabsContent } from "@workspace/ui/components/tabs"

type SecurityItemsQuery = {
  data?: PipelineItemListResponse
  isLoading: boolean
  isFetching: boolean
  refetch: () => Promise<unknown>
}

type EventQuery = {
  refetch: () => Promise<unknown>
}

export function SecurityAccountsTab({
  data,
  items,
  events,
  refresh,
  refreshing,
}: {
  data: PipelineRunDetail
  items: SecurityItemsQuery
  events: EventQuery
  refresh: () => void
  refreshing: boolean
}) {
  const routeState = usePipelineRunRouteState()
  const [selected, setSelected] = useState<string[]>([])
  const page = routeState.itemPage
  const pageSize = 50
  const rows = items.data?.items ?? []
  const pageCount = Math.max(1, Math.ceil((items.data?.total ?? 0) / pageSize))
  const selectedRows = rows.filter((item) => selected.includes(item.id))
  const failedIds = selectedRows
    .filter((item) => item.status === "failed")
    .map((item) => item.id)
  const completedIds = selectedRows
    .filter(
      (item) =>
        ["set", "available"].includes(item.password_status ?? "") &&
        item.mfa_status === "enabled"
    )
    .map((item) => item.id)

  const checkPlus = useMutation<
    ResultOperationSummary,
    ApiError,
    { emails?: string[]; allRun?: boolean }
  >({
    mutationFn: ({ emails = [], allRun = false }) =>
      runResultOperation("/api/results/check-plus", {
        emails,
        all: false,
        proxy: "",
        pipeline_run_id: allRun ? data.id : null,
      }),
    onSuccess: (result) => {
      refresh()
      void items.refetch()
      toast.success(
        `Plus 检查完成：确认 Plus ${result.plus}/${result.total}${result.unknown ? `，无法确认 ${result.unknown}` : ""}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const retry = useMutation<
    { processed: number; skipped: number },
    ApiError,
    string[]
  >({
    mutationFn: (itemIds) =>
      apiRequest(
        `/api/pipelines/runs/${encodeURIComponent(data.id)}/items/retry`,
        {
          method: "POST",
          data: { item_ids: itemIds },
        }
      ),
    onSuccess: (result) => {
      setSelected([])
      refresh()
      void items.refetch()
      void events.refetch()
      toast.success(
        `已重新排队 ${result.processed} 项，跳过 ${result.skipped} 项`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const copy = useMutation<
    {
      text: string
      copied: number
      skipped: number
      duplicates: number
      plus_restricted: number
      copy_marks: Array<{ email: string; fingerprint: string }>
    },
    ApiError,
    { itemIds?: string[]; all?: boolean }
  >({
    mutationFn: ({ itemIds = [], all = false }) =>
      apiRequest(
        `/api/pipelines/runs/${encodeURIComponent(data.id)}/security-credentials/copy`,
        {
          method: "POST",
          data: { item_ids: itemIds, all_completed: all },
        }
      ),
    onSuccess: async (result) => {
      if (!result.copied) {
        toast.info(
          result.plus_restricted
            ? `没有可复制的安全凭证，${result.plus_restricted} 条未确认是 Plus`
            : result.duplicates
              ? `没有新的安全凭证，${result.duplicates} 条已经复制过`
              : "没有可复制的安全凭证"
        )
        return
      }
      await navigator.clipboard.writeText(result.text)
      try {
        await apiRequest(
          `/api/pipelines/runs/${encodeURIComponent(data.id)}/deliveries/copy/confirm`,
          { method: "POST", data: { copy_marks: result.copy_marks } }
        )
      } catch {
        toast.warning("内容已复制，但复制记录保存失败")
      }
      setSelected([])
      toast.success(
        `已复制 ${result.copied} 条安全凭证${result.skipped ? `，跳过 ${result.skipped} 条${result.plus_restricted ? `（未确认 Plus ${result.plus_restricted}）` : ""}` : ""}`
      )
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <TabsContent
      className="mt-3 flex min-h-0 flex-1 flex-col border-t"
      value="items"
    >
      <div className="flex min-h-12 flex-wrap items-center justify-end gap-2 border-b py-2">
        {selected.length > 0 && (
          <>
            <span className="text-xs font-medium">
              已选 {selected.length} 项
            </span>
            <Button
              disabled={!completedIds.length || copy.isPending}
              onClick={() => copy.mutate({ itemIds: completedIds })}
              size="sm"
              variant="outline"
            >
              <Clipboard />
              复制安全凭证 {completedIds.length}
            </Button>
            <Button
              disabled={checkPlus.isPending}
              onClick={() =>
                checkPlus.mutate({
                  emails: selectedRows
                    .map((item) => item.account_email)
                    .filter((email): email is string => Boolean(email)),
                })
              }
              size="sm"
              variant="outline"
            >
              <ShieldCheck />
              严格检查 Plus
            </Button>
            <Button
              disabled={!failedIds.length || retry.isPending}
              onClick={() => retry.mutate(failedIds)}
              size="sm"
              variant="outline"
            >
              <RefreshCw />
              重试失败项 {failedIds.length}
            </Button>
            <Button
              aria-label="清除选择"
              onClick={() => setSelected([])}
              size="icon-sm"
              variant="ghost"
            >
              <X />
            </Button>
          </>
        )}
        <Button
          disabled={copy.isPending || data.registered_count === 0}
          onClick={() => copy.mutate({ all: true })}
          size="sm"
        >
          <Clipboard />
          复制全部安全凭证
        </Button>
        <Button
          disabled={checkPlus.isPending || (items.data?.total ?? 0) === 0}
          onClick={() => checkPlus.mutate({ allRun: true })}
          size="sm"
          variant="outline"
        >
          <ShieldCheck />
          严格检查全部 Plus
        </Button>
        <TableRefreshButton
          isRefreshing={refreshing || items.isFetching}
          label="刷新安全处理状态"
          onRefresh={() => {
            refresh()
            void items.refetch()
          }}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Table className="min-w-220">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <SelectionCheckbox
                  ids={rows.map((item) => item.id)}
                  selected={selected}
                  setSelected={setSelected}
                />
              </TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>处理状态</TableHead>
              <TableHead>密码</TableHead>
              <TableHead>MFA</TableHead>
              <TableHead>Plus</TableHead>
              <TableHead>错误</TableHead>
              <TableHead>更新时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => {
              const passwordComplete = ["set", "available"].includes(
                item.password_status ?? ""
              )
              const mfaComplete = item.mfa_status === "enabled"
              const partial =
                item.status === "failed" && (passwordComplete || mfaComplete)
              return (
                <TableRow key={item.id}>
                  <TableCell>
                    <RowCheckbox
                      id={item.id}
                      selected={selected}
                      setSelected={setSelected}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {item.account_email}
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={partial ? "partial" : item.status}
                      label={
                        partial ? "部分成功" : TASK_STATUS_LABELS[item.status]
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={passwordComplete ? "set" : "not_set"}
                      label={passwordComplete ? "已设置" : "未完成"}
                    />
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={mfaComplete ? "enabled" : "not_enabled"}
                      label={mfaComplete ? "已启用" : "未完成"}
                    />
                  </TableCell>
                  <TableCell>
                    <PlusStateBadge
                      state={item.plus_state}
                      label={item.plus_label}
                      error={item.plus_error}
                    />
                  </TableCell>
                  <TableCell
                    className="max-w-96 truncate text-xs text-destructive"
                    title={item.security_error ?? item.error ?? undefined}
                  >
                    {item.security_error || item.error || "-"}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatCompactBeijingDateTime(item.updated_at)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
      <TablePagination
        page={page}
        pageCount={pageCount}
        total={items.data?.total ?? 0}
        onPageChange={(value) => {
          routeState.setItemPage(value)
          setSelected([])
        }}
      />
    </TabsContent>
  )
}
