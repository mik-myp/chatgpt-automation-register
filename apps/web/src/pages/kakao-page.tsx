import { useDeferredValue, useState } from "react"
import { Link } from "react-router"
import { useMutation, useQuery } from "@tanstack/react-query"
import {
  Ban,
  ChevronRight,
  ExternalLink,
  Eye,
  Inbox,
  Play,
  RefreshCw,
  Search,
  X,
} from "lucide-react"
import { toast } from "sonner"

import {
  KakaoTaskStatus,
  getListKakaoTasksApiKakaoTasksGetQueryKey,
  type KakaoTaskStatus as KakaoTaskStatusType,
  useListKakaoTasksApiKakaoTasksGet,
} from "@/api/generated"
import { TablePagination } from "@/components/table-pagination"
import { ApiError, apiRequest } from "@/lib/api-client"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  extracting: "提取中",
  done: "完成",
  failed: "失败",
  canceled: "已取消",
}

type TaskAction = "sync" | "retry" | "cancel"

export function KakaoPage() {
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState<KakaoTaskStatusType | "all">("all")
  const [paymentStatus, setPaymentStatus] = useState("")
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(50)
  const [selected, setSelected] = useState<string[]>([])
  const [detailOpen, setDetailOpen] = useState(false)
  const deferredSearch = useDeferredValue(search.trim())
  const deferredPayment = useDeferredValue(paymentStatus.trim())
  const taskParams = {
    search: deferredSearch || undefined,
    status: status === "all" ? undefined : status,
    payment_status: deferredPayment || undefined,
    limit: pageSize,
    offset: page * pageSize,
  }
  const tasks = useListKakaoTasksApiKakaoTasksGet(taskParams, {
    query: {
      queryKey: getListKakaoTasksApiKakaoTasksGetQueryKey(taskParams),
      refetchInterval: 5000,
    },
  })
  const rows = tasks.data?.items ?? []
  const activePaymentIds = rows
    .filter(
      (task) =>
        task.status === "done" &&
        Boolean(task.payment_url) &&
        !["succeeded", "failed", "canceled", "expired"].includes(
          task.payment_status ?? ""
        )
    )
    .map((task) => task.id)
  useQuery({
    queryKey: ["/api/kakao/tasks/payment-sync", activePaymentIds],
    queryFn: async () => {
      const result = await apiRequest<{ processed: number; failed: number }>(
        "/api/kakao/tasks/payment-sync",
        { method: "POST", data: { task_ids: activePaymentIds } }
      )
      await tasks.refetch()
      return result
    },
    enabled: activePaymentIds.length > 0,
    refetchInterval: 3000,
  })
  const ids = rows.map((task) => task.id)
  const selectedOnPage = ids.filter((id) => selected.includes(id)).length
  const pageCount = Math.max(1, Math.ceil((tasks.data?.total ?? 0) / pageSize))

  const action = useMutation<
    { processed: number; failed?: number },
    ApiError,
    { action: TaskAction; ids?: string[] }
  >({
    mutationFn: async ({ action, ids: explicitIds }) => {
      const taskIds = explicitIds ?? selected
      if (action === "sync") {
        return apiRequest<{ processed: number; failed?: number }>(
          "/api/kakao/tasks/sync",
          { method: "POST", data: { task_ids: taskIds } }
        )
      }
      const values = await Promise.all(
        taskIds.map((taskId) =>
          apiRequest<{ processed: number; failed?: number }>(
            `/api/kakao/tasks/${encodeURIComponent(taskId)}/${action}`,
            { method: "POST" }
          )
        )
      )
      return {
        processed: values.reduce((sum, value) => sum + value.processed, 0),
        failed: values.reduce((sum, value) => sum + (value.failed ?? 0), 0),
      }
    },
    onSuccess: (result, variables) => {
      void tasks.refetch()
      setSelected([])
      const label =
        variables.action === "sync"
          ? "同步"
          : variables.action === "retry"
            ? "重试"
            : "取消"
      toast.success(
        `${label}完成：处理 ${result.processed}，失败 ${result.failed ?? 0}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const detail = useMutation<unknown, ApiError, string>({
    mutationFn: (taskId) =>
      apiRequest(`/api/kakao/tasks/${encodeURIComponent(taskId)}/details`, {
        timeout: 120_000,
      }),
    onSuccess: () => setDetailOpen(true),
    onError: (error) => toast.error(error.message),
  })

  const resetPage = () => {
    setPage(0)
    setSelected([])
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Kakao 任务</h1>
        <Button
          disabled={action.isPending || !rows.length}
          onClick={() =>
            action.mutate({ action: "sync", ids: rows.map((task) => task.id) })
          }
          size="sm"
          variant="outline"
        >
          <RefreshCw />
          同步当前页
        </Button>
      </div>
      <section className="flex min-h-0 flex-1 flex-col border-t">
        <div className="flex flex-wrap items-center gap-2 border-b py-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="搜索 Kakao 任务"
              className="pl-8"
              onChange={(event) => {
                setSearch(event.target.value)
                resetPage()
              }}
              placeholder="搜索邮箱、任务 ID 或错误"
              value={search}
            />
          </div>
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value as typeof status)
              resetPage()
            }}
          >
            <SelectTrigger aria-label="任务状态" className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              {Object.values(KakaoTaskStatus).map((value) => (
                <SelectItem key={value} value={value}>
                  {STATUS_LABELS[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            aria-label="支付状态"
            className="w-36"
            onChange={(event) => {
              setPaymentStatus(event.target.value)
              resetPage()
            }}
            placeholder="支付状态"
            value={paymentStatus}
          />
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
            <span className="text-xs text-muted-foreground">
              筛选结果 {tasks.data?.total ?? 0} 条
            </span>
            {selected.length > 0 && (
              <>
                <span className="text-xs font-medium">
                  已选 {selected.length} 项
                </span>
                <Button
                  disabled={action.isPending}
                  onClick={() => action.mutate({ action: "sync" })}
                  size="sm"
                  variant="outline"
                >
                  <RefreshCw />
                  同步
                </Button>
                <Button
                  disabled={action.isPending}
                  onClick={() => action.mutate({ action: "retry" })}
                  size="sm"
                  variant="outline"
                >
                  <Play />
                  重试
                </Button>
                <Button
                  disabled={action.isPending}
                  onClick={() => action.mutate({ action: "cancel" })}
                  size="sm"
                  variant="outline"
                >
                  <Ban />
                  取消
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
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Table className="min-w-240">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    aria-label="选择当前页全部任务"
                    checked={
                      ids.length > 0 && selectedOnPage === ids.length
                        ? true
                        : selectedOnPage > 0
                          ? "indeterminate"
                          : false
                    }
                    onCheckedChange={(checked) =>
                      setSelected(checked ? ids : [])
                    }
                  />
                </TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>任务 ID</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>支付状态</TableHead>
                <TableHead>扣卡</TableHead>
                <TableHead>流水线轮次</TableHead>
                <TableHead>更新时间</TableHead>
                <TableHead className="w-40 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((task) => (
                <TableRow key={task.id}>
                  <TableCell>
                    <Checkbox
                      aria-label={`选择 ${task.upstream_job_id}`}
                      checked={selected.includes(task.id)}
                      onCheckedChange={() =>
                        setSelected(
                          selected.includes(task.id)
                            ? selected.filter((id) => id !== task.id)
                            : [...selected, task.id]
                        )
                      }
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {task.email}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {task.upstream_job_id}
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={task.status}
                      label={STATUS_LABELS[task.status]}
                    />
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={task.payment_status}
                      label={
                        {
                          ready: "等待扫码",
                          waiting: "等待扫码",
                          opened: "已扫码",
                          succeeded: "支付成功",
                          failed: "支付失败",
                          canceled: "已取消",
                          expired: "已过期",
                        }[task.payment_status ?? ""] ?? "未知"
                      }
                    />
                  </TableCell>
                  <TableCell>
                    {task.card_charged == null
                      ? "-"
                      : task.card_charged
                        ? "是"
                        : "否"}
                  </TableCell>
                  <TableCell>
                    {task.pipeline_run_id ? (
                      <Button asChild size="sm" variant="link">
                        <Link to={`/pipelines/${task.pipeline_run_id}`}>
                          {task.pipeline_run_id.slice(0, 8)}
                          <ChevronRight />
                        </Link>
                      </Button>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {new Date(task.updated_at).toLocaleString("zh-CN")}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      aria-label="查看任务详情"
                      onClick={() => detail.mutate(task.id)}
                      size="icon-sm"
                      title="查看详情"
                      variant="ghost"
                    >
                      <Eye />
                    </Button>
                    <Button
                      aria-label="重试任务"
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({ action: "retry", ids: [task.id] })
                      }
                      size="icon-sm"
                      title="重试"
                      variant="ghost"
                    >
                      <Play />
                    </Button>
                    <Button
                      aria-label="取消任务"
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({ action: "cancel", ids: [task.id] })
                      }
                      size="icon-sm"
                      title="取消"
                      variant="ghost"
                    >
                      <Ban />
                    </Button>
                    {task.payment_url && (
                      <Button
                        asChild
                        aria-label="打开支付链接"
                        size="icon-sm"
                        variant="ghost"
                      >
                        <a
                          href={task.payment_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          <ExternalLink />
                        </a>
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {!tasks.isLoading && !rows.length && (
                <TableRow>
                  <TableCell className="h-52 text-center" colSpan={9}>
                    <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                    <p className="text-sm font-medium">暂无 Kakao 任务</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <TablePagination
          onPageChange={(value) => {
            setPage(value)
            setSelected([])
          }}
          onPageSizeChange={(value) => {
            setPageSize(value)
            resetPage()
          }}
          page={page}
          pageCount={pageCount}
          pageSize={pageSize}
        />
      </section>
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Kakao 任务详情</DialogTitle>
            <DialogDescription>
              本地记录、上游任务与 Kakao 深层状态
            </DialogDescription>
          </DialogHeader>
          <pre className="overflow-auto rounded-sm bg-muted/40 p-3 font-mono text-xs break-all whitespace-pre-wrap">
            {JSON.stringify(detail.data, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  )
}
