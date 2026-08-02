import { useState } from "react"
import { Link } from "react-router"
import { useMutation } from "@tanstack/react-query"
import { ArrowLeft, Clipboard, RefreshCw, ShieldCheck, X } from "lucide-react"
import { toast } from "sonner"

import { type PipelineRunDetail } from "@/api/generated"
import {
  RuntimeEventLog,
  type RuntimeEvent,
} from "@/components/pipelines/runtime-event-log"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import {
  PlusStateBadge,
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import { usePipelineRunRouteState } from "@/features/pipelines/hooks/use-pipeline-run-route-state"
import {
  pipelineStatus,
  type StrictPlusCheckResponse,
  TASK_STATUS_LABELS,
} from "@/features/pipelines/lib/pipeline-state"
import { ApiError, apiRequest } from "@/lib/api-client"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { Button } from "@workspace/ui/components/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"

export function SecurityPipelineRunView({
  data,
  events,
  refresh,
  refreshing,
}: {
  data: PipelineRunDetail
  events: { data?: { items: RuntimeEvent[] }; isLoading: boolean }
  refresh: () => void
  refreshing: boolean
}) {
  const routeState = usePipelineRunRouteState()
  const activeTab = routeState.activeTab === "events" ? "events" : "items"
  const [selected, setSelected] = useState<string[]>([])
  const page = routeState.itemPage
  const pageSize = 50
  const rows = data.items.slice(page * pageSize, (page + 1) * pageSize)
  const pageCount = Math.max(1, Math.ceil(data.items.length / pageSize))
  const selectedRows = data.items.filter((item) => selected.includes(item.id))
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
  const checkPlus = useMutation<StrictPlusCheckResponse, ApiError, string[]>({
    mutationFn: (emails) =>
      apiRequest<StrictPlusCheckResponse>("/api/results/check-plus", {
        method: "POST",
        data: { emails, all: false, proxy: "" },
      }),
    onSuccess: (result) => {
      refresh()
      const plus = result.items.filter((item) => item.is_plus === true).length
      const unknown = result.items.filter((item) => item.is_plus == null).length
      toast.success(
        `Plus 检查完成：确认 Plus ${plus}/${result.items.length}${unknown ? `，无法确认 ${unknown}` : ""}`
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
        { method: "POST", data: { item_ids: itemIds } }
      ),
    onSuccess: (result) => {
      setSelected([])
      refresh()
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
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex min-w-0 items-center gap-3">
        <Button
          asChild
          aria-label="返回流水线轮次"
          size="icon-sm"
          variant="outline"
        >
          <Link to="/pipelines">
            <ArrowLeft />
          </Link>
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate font-mono text-base font-semibold">
              {data.id}
            </h1>
            <StatusBadge status="account_security" label="安全处理" />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge {...pipelineStatus(data)} />
            {data.source_pipeline_run_id && (
              <Link
                className="text-xs text-muted-foreground hover:underline"
                to={`/pipelines/${data.source_pipeline_run_id}`}
              >
                来源注册轮次 {data.source_pipeline_run_id.slice(0, 8)}
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-4">
        {[
          ["账号", data.target_count],
          ["完成", data.registered_count],
          ["失败或部分成功", data.failed_count],
          [
            "处理中",
            data.items.filter((item) =>
              ["scheduled", "registering"].includes(item.status)
            ).length,
          ],
        ].map(([label, value], index) => (
          <div className={`px-4 py-4 ${index ? "border-l" : ""}`} key={label}>
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 font-mono text-xl font-semibold tabular-nums">
              {value}
            </div>
          </div>
        ))}
      </div>

      <Tabs
        className="flex min-h-0 flex-1 flex-col"
        value={activeTab}
        onValueChange={routeState.setActiveTab}
      >
        <TabsList className="w-full justify-start">
          <TabsTrigger value="items">安全处理账号</TabsTrigger>
          <TabsTrigger value="events">运行日志</TabsTrigger>
        </TabsList>
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
                    checkPlus.mutate(
                      selectedRows
                        .map((item) => item.account_email)
                        .filter((email): email is string => Boolean(email))
                    )
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
              disabled={checkPlus.isPending || data.items.length === 0}
              onClick={() =>
                checkPlus.mutate(
                  data.items
                    .map((item) => item.account_email)
                    .filter((email): email is string => Boolean(email))
                )
              }
              size="sm"
              variant="outline"
            >
              <ShieldCheck />
              严格检查全部 Plus
            </Button>
            <TableRefreshButton
              isRefreshing={refreshing}
              label="刷新安全处理状态"
              onRefresh={refresh}
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
                    item.status === "failed" &&
                    (passwordComplete || mfaComplete)
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
                            partial
                              ? "部分成功"
                              : TASK_STATUS_LABELS[item.status]
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
            total={data.items.length}
            onPageChange={(value) => {
              routeState.setItemPage(value)
              setSelected([])
            }}
          />
        </TabsContent>
        <TabsContent
          className="mt-3 min-h-0 flex-1 overflow-hidden border"
          value="events"
        >
          <RuntimeEventLog
            events={events.data?.items ?? []}
            loading={events.isLoading}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
