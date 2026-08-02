import { Fragment, useState } from "react"
import { Link, useParams } from "react-router"
import { useMutation, useQuery } from "@tanstack/react-query"
import {
  ArrowLeft,
  Ban,
  ChevronRight,
  ExternalLink,
  Eye,
  LinkIcon,
  Mail,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react"
import { toast } from "sonner"

import {
  getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey,
  getListKakaoTasksApiKakaoTasksGetQueryKey,
  KakaoTaskStatus,
  type PipelineDeliverySummary,
  PipelineRunKind,
  useGetPipelineRunApiPipelinesRunsRunIdGet,
  useListKakaoTasksApiKakaoTasksGet,
} from "@/api/generated"
import {
  RuntimeEventLog,
  type RuntimeEvent,
} from "@/components/pipelines/runtime-event-log"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import {
  CopySelectionBar,
  PlusStateBadge,
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import {
  pipelineStatus,
  type StrictPlusCheckResponse,
  TASK_STATUS_LABELS,
} from "@/features/pipelines/lib/pipeline-state"
import { SecurityPipelineRunView } from "@/features/pipelines/pages/security-pipeline-run-view"
import { ApiError, apiRequest } from "@/lib/api-client"
import { isTerminalPaymentStatus, paymentStatusLabel } from "@/lib/kakao-status"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"

export function PipelineRunPage() {
  const { runId = "" } = useParams()
  const pageSize = 50
  const [itemPage, setItemPage] = useState(0)
  const [taskPage, setTaskPage] = useState(0)
  const [cardPage, setCardPage] = useState(0)
  const [deliveryPage, setDeliveryPage] = useState(0)
  const [activeTab, setActiveTab] = useState("items")
  const [itemSelection, setItemSelection] = useState<string[]>([])
  const [taskSelection, setTaskSelection] = useState<string[]>([])
  const [cardSelection, setCardSelection] = useState<string[]>([])
  const [deliverySelection, setDeliverySelection] = useState<string[]>([])
  const [taskStatus, setTaskStatus] = useState<KakaoTaskStatus | "all">("all")
  const [taskDetailOpen, setTaskDetailOpen] = useState(false)
  const run = useGetPipelineRunApiPipelinesRunsRunIdGet(runId, {
    query: {
      queryKey: getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey(runId),
      refetchInterval: 2000,
    },
  })
  const events = useQuery({
    queryKey: ["/api/pipelines/runs", runId, "events"],
    queryFn: () =>
      apiRequest<{
        items: RuntimeEvent[]
        last_sequence: number
        terminal: boolean
      }>(`/api/pipelines/runs/${encodeURIComponent(runId)}/events?limit=500`),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.terminal ? false : 1000),
  })
  const taskParams = {
    pipeline_run_id: runId,
    status: taskStatus === "all" ? undefined : taskStatus,
    limit: pageSize,
    offset: taskPage * pageSize,
  }
  const tasks = useListKakaoTasksApiKakaoTasksGet(taskParams, {
    query: {
      queryKey: getListKakaoTasksApiKakaoTasksGetQueryKey(taskParams),
      enabled:
        Boolean(runId) && run.data?.kind !== PipelineRunKind.account_security,
    },
  })
  const deliveries = useQuery({
    queryKey: ["/api/pipelines/runs", runId, "deliveries", deliveryPage],
    queryFn: () =>
      apiRequest<{
        items: PipelineDeliverySummary[]
        total: number
        limit: number
        offset: number
      }>(
        `/api/pipelines/runs/${encodeURIComponent(runId)}/deliveries?limit=${pageSize}&offset=${deliveryPage * pageSize}`
      ),
    enabled:
      Boolean(runId) && run.data?.kind !== PipelineRunKind.account_security,
    refetchInterval: activeTab === "delivery" ? 3000 : false,
  })
  const hasActivePayment = (deliveries.data?.items ?? []).some(
    (item) =>
      item.task_status === "done" &&
      Boolean(item.payment_url) &&
      !isTerminalPaymentStatus(item.payment_status)
  )
  useQuery({
    queryKey: ["/api/kakao/tasks/payment-sync", runId],
    queryFn: () =>
      apiRequest<{ processed: number; failed: number }>(
        "/api/kakao/tasks/payment-sync",
        { method: "POST", data: { task_ids: [], pipeline_run_id: runId } }
      ),
    enabled:
      Boolean(runId) &&
      run.data?.kind !== PipelineRunKind.account_security &&
      activeTab === "delivery" &&
      hasActivePayment,
    refetchInterval: 3000,
  })
  const copyDeliveries = useMutation<
    {
      text: string
      copied: number
      skipped: number
      security_credentials: number
      mail_access: number
      missing_mail_url: number
      duplicates: number
      plus_restricted: number
      copy_marks: Array<{ email: string; fingerprint: string }>
    },
    ApiError,
    {
      copyType: "payment_links" | "account_info"
      taskIds?: string[]
      all?: boolean
    }
  >({
    mutationFn: ({ copyType, taskIds = [], all = false }) =>
      apiRequest(
        `/api/pipelines/runs/${encodeURIComponent(runId)}/deliveries/copy`,
        {
          method: "POST",
          data: {
            task_ids: taskIds,
            all_deliverable: all,
            copy_type: copyType,
          },
        }
      ),
    onSuccess: async (result, variables) => {
      const label =
        variables.copyType === "payment_links" ? "支付链接" : "邮箱信息"
      if (!result.copied) {
        const reason = result.plus_restricted
          ? `：${result.plus_restricted} 条未确认是 Plus`
          : result.missing_mail_url
            ? `：${result.missing_mail_url} 条缺少邮件查询地址`
            : result.duplicates
              ? `：${result.duplicates} 条已经复制过`
              : ""
        toast.error(`没有可复制的${label}${reason}`)
        return
      }
      await navigator.clipboard.writeText(result.text)
      if (variables.copyType === "account_info" && result.copy_marks.length) {
        try {
          await apiRequest(
            `/api/pipelines/runs/${encodeURIComponent(runId)}/deliveries/copy/confirm`,
            {
              method: "POST",
              data: { copy_marks: result.copy_marks },
            }
          )
        } catch {
          toast.warning("内容已复制，但复制记录保存失败，下次可能出现重复数据")
        }
      }
      setDeliverySelection([])
      const accountBreakdown =
        variables.copyType === "account_info"
          ? `（安全凭证 ${result.security_credentials}，邮箱访问 ${result.mail_access}）`
          : ""
      const skipped = result.skipped
        ? `，跳过 ${result.skipped} 条${result.plus_restricted ? `（未确认 Plus ${result.plus_restricted}）` : result.duplicates ? `（重复或已复制 ${result.duplicates}）` : result.missing_mail_url ? `（缺少邮件查询地址 ${result.missing_mail_url}）` : ""}`
        : ""
      toast.success(
        `已复制 ${result.copied} 条${label}${accountBreakdown}${skipped}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const checkPlus = useMutation<StrictPlusCheckResponse, ApiError, string[]>({
    mutationFn: (emails) =>
      apiRequest<StrictPlusCheckResponse>("/api/results/check-plus", {
        method: "POST",
        data: { emails, all: false, proxy: "" },
      }),
    onSuccess: (result) => {
      void run.refetch()
      void deliveries.refetch()
      const plus = result.items.filter((item) => item.is_plus === true).length
      const unknown = result.items.filter((item) => item.is_plus == null).length
      toast.success(
        `Plus 检查完成：确认 Plus ${plus}/${result.items.length}${unknown ? `，无法确认 ${unknown}` : ""}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const taskAction = useMutation<
    { processed: number; failed?: number },
    ApiError,
    { action: "sync" | "cancel" | "retry"; ids?: string[] }
  >({
    mutationFn: async ({ action, ids }) => {
      const taskIds = ids ?? taskSelection
      if (action === "sync") {
        return apiRequest<{ processed: number; failed?: number }>(
          "/api/kakao/tasks/sync",
          {
            method: "POST",
            data: { task_ids: taskIds },
          }
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
        processed: values.reduce((total, value) => total + value.processed, 0),
        failed: values.reduce((total, value) => total + (value.failed ?? 0), 0),
      }
    },
    onSuccess: (result, variables) => {
      void tasks.refetch()
      const label =
        variables.action === "sync"
          ? "同步"
          : variables.action === "cancel"
            ? "取消"
            : "重试"
      toast.success(`${label}完成：处理 ${result.processed}`)
    },
    onError: (error) => toast.error(error.message),
  })
  const taskDetail = useMutation<unknown, ApiError, string>({
    mutationFn: (taskId) =>
      apiRequest(`/api/kakao/tasks/${encodeURIComponent(taskId)}/details`, {
        timeout: 120_000,
      }),
    onSuccess: () => setTaskDetailOpen(true),
    onError: (error) => toast.error(error.message),
  })
  const retryItems = useMutation<
    { processed: number; skipped: number },
    ApiError,
    string[]
  >({
    mutationFn: (itemIds) =>
      apiRequest<{ processed: number; skipped: number }>(
        `/api/pipelines/runs/${encodeURIComponent(runId)}/items/retry`,
        {
          method: "POST",
          data: { item_ids: itemIds },
        }
      ),
    onSuccess: (result) => {
      setItemSelection([])
      void run.refetch()
      toast.success(
        `已重新排队 ${result.processed} 项，跳过 ${result.skipped} 项`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const data = run.data
  if (run.isError) {
    return <div className="text-sm text-destructive">无法读取该流水线轮次</div>
  }
  if (!data) {
    return <div className="text-sm text-muted-foreground">正在读取轮次...</div>
  }
  if (data.kind === PipelineRunKind.account_security) {
    return (
      <SecurityPipelineRunView
        data={data}
        events={events}
        refresh={() => void run.refetch()}
        refreshing={run.isFetching}
      />
    )
  }

  const selectedItems = data.items.filter((item) =>
    itemSelection.includes(item.id)
  )
  const selectedTasks = (tasks.data?.items ?? []).filter((task) =>
    taskSelection.includes(task.id)
  )
  const selectedCards = data.cards.filter((card) =>
    cardSelection.includes(card.card_id)
  )
  const deliveryRows = deliveries.data?.items ?? []
  const itemRows = data.items.slice(
    itemPage * pageSize,
    (itemPage + 1) * pageSize
  )
  const taskRows = tasks.data?.items ?? []
  const cardRows = data.cards.slice(
    cardPage * pageSize,
    (cardPage + 1) * pageSize
  )
  const itemPageCount = Math.max(1, Math.ceil(data.items.length / pageSize))
  const taskPageCount = Math.max(
    1,
    Math.ceil((tasks.data?.total ?? 0) / pageSize)
  )
  const cardPageCount = Math.max(1, Math.ceil(data.cards.length / pageSize))
  const deliveryPageCount = Math.max(
    1,
    Math.ceil((deliveries.data?.total ?? 0) / pageSize)
  )

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
        <div className="min-w-0">
          <h1 className="truncate font-mono text-base font-semibold">
            {data.id}
          </h1>
          <StatusBadge className="mt-1" {...pipelineStatus(data)} />
        </div>
        {data.registered_count > 0 && (
          <div className="ml-auto">
            <CreateSecurityPipelineDialog sourceRunId={data.id} />
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-5">
        {[
          ["目标", data.target_count],
          ["已调度", data.scheduled_count],
          ["注册成功", data.registered_count],
          ["失败", data.failed_count],
          ["Kakao 任务", data.kakao_task_count],
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
        onValueChange={setActiveTab}
      >
        <TabsList className="w-full justify-start">
          <TabsTrigger className="shrink-0" value="items">
            注册项
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="kakao">
            Kakao 任务
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="delivery">
            交付信息
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="cards">
            卡密分配
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="events">
            运行日志
          </TabsTrigger>
        </TabsList>
        <TabsContent
          value="items"
          className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
        >
          <div className="flex min-h-12 items-center border-b py-2">
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              <CopySelectionBar
                selected={itemSelection}
                values={selectedItems
                  .map((item) => item.account_email)
                  .filter((value): value is string => Boolean(value))}
                label="邮箱"
                clear={() => setItemSelection([])}
              />
              {itemSelection.length > 0 && (
                <Button
                  disabled={retryItems.isPending}
                  onClick={() => retryItems.mutate(itemSelection)}
                  size="sm"
                  variant="outline"
                >
                  <RefreshCw />
                  重跑失败项
                </Button>
              )}
              <TableRefreshButton
                isRefreshing={run.isFetching}
                label="刷新注册项"
                onRefresh={() => void run.refetch()}
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <Table className="min-w-220">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <SelectionCheckbox
                      ids={itemRows.map((item) => item.id)}
                      selected={itemSelection}
                      setSelected={setItemSelection}
                    />
                  </TableHead>
                  <TableHead>序号</TableHead>
                  <TableHead>邮箱</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>资格</TableHead>
                  <TableHead>错误</TableHead>
                  <TableHead className="w-14 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {itemRows.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <RowCheckbox
                        id={item.id}
                        selected={itemSelection}
                        setSelected={setItemSelection}
                      />
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {item.position + 1}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {item.account_email ?? "-"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={item.status}
                        label={TASK_STATUS_LABELS[item.status]}
                      />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {item.eligibility_state ?? "-"}
                    </TableCell>
                    <TableCell className="max-w-72 truncate text-xs text-red-600">
                      {item.error ?? "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      {(item.status === "failed" ||
                        item.status === "skipped") && (
                        <Button
                          aria-label={`重跑第 ${item.position + 1} 项`}
                          disabled={retryItems.isPending}
                          onClick={() => retryItems.mutate([item.id])}
                          size="icon-sm"
                          title="重跑"
                          variant="ghost"
                        >
                          <RefreshCw />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!data.items.length && (
                  <TableRow>
                    <TableCell
                      className="h-40 text-center text-sm text-muted-foreground"
                      colSpan={7}
                    >
                      本轮次暂无注册项
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          <TablePagination
            page={itemPage}
            pageCount={itemPageCount}
            total={data.items.length}
            onPageChange={(value) => {
              setItemPage(value)
              setItemSelection([])
            }}
          />
        </TabsContent>

        <TabsContent
          value="kakao"
          className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
        >
          <div className="flex min-h-12 items-center border-b py-2">
            <Select
              value={taskStatus}
              onValueChange={(value) => {
                setTaskStatus(value as typeof taskStatus)
                setTaskPage(0)
                setTaskSelection([])
              }}
            >
              <SelectTrigger
                aria-label="Kakao 任务状态"
                className="mr-2 w-32"
                size="sm"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                {Object.entries(KakaoTaskStatus).map(([, value]) => (
                  <SelectItem key={value} value={value}>
                    {TASK_STATUS_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              <CopySelectionBar
                selected={taskSelection}
                values={selectedTasks.map((task) => task.upstream_job_id)}
                label="任务 ID"
                clear={() => setTaskSelection([])}
              />
              {taskSelection.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <Button
                    disabled={taskAction.isPending}
                    onClick={() => taskAction.mutate({ action: "sync" })}
                    size="sm"
                    variant="outline"
                  >
                    <RefreshCw />
                    同步
                  </Button>
                  <Button
                    disabled={taskAction.isPending}
                    onClick={() => taskAction.mutate({ action: "retry" })}
                    size="sm"
                    variant="outline"
                  >
                    <Play />
                    重试
                  </Button>
                  <Button
                    disabled={taskAction.isPending}
                    onClick={() => taskAction.mutate({ action: "cancel" })}
                    size="sm"
                    variant="outline"
                  >
                    <Ban />
                    取消
                  </Button>
                </div>
              )}
              <TableRefreshButton
                isRefreshing={tasks.isFetching}
                label="刷新 Kakao 任务"
                onRefresh={() => void tasks.refetch()}
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <Table className="min-w-190">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <SelectionCheckbox
                      ids={taskRows.map((task) => task.id)}
                      selected={taskSelection}
                      setSelected={setTaskSelection}
                    />
                  </TableHead>
                  <TableHead>邮箱</TableHead>
                  <TableHead>任务 ID</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>支付状态</TableHead>
                  <TableHead>扣卡</TableHead>
                  <TableHead className="w-32 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {taskRows.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>
                      <RowCheckbox
                        id={task.id}
                        selected={taskSelection}
                        setSelected={setTaskSelection}
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
                        label={TASK_STATUS_LABELS[task.status]}
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={task.payment_status}
                        label={paymentStatusLabel(task.payment_status)}
                      />
                    </TableCell>
                    <TableCell>
                      {task.card_charged == null
                        ? "-"
                        : task.card_charged
                          ? "是"
                          : "否"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        aria-label="查看任务详情"
                        onClick={() => taskDetail.mutate(task.id)}
                        size="icon-sm"
                        title="查看详情"
                        variant="ghost"
                      >
                        <Eye />
                      </Button>
                      <Button
                        aria-label="重试任务"
                        disabled={taskAction.isPending}
                        onClick={() =>
                          taskAction.mutate({ action: "retry", ids: [task.id] })
                        }
                        size="icon-sm"
                        title="重试"
                        variant="ghost"
                      >
                        <Play />
                      </Button>
                      <Button
                        aria-label="取消任务"
                        disabled={taskAction.isPending}
                        onClick={() =>
                          taskAction.mutate({
                            action: "cancel",
                            ids: [task.id],
                          })
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
                {!tasks.isLoading && !tasks.data?.items.length && (
                  <TableRow>
                    <TableCell
                      className="h-40 text-center text-sm text-muted-foreground"
                      colSpan={7}
                    >
                      本轮次暂无 Kakao 任务
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          <TablePagination
            page={taskPage}
            pageCount={taskPageCount}
            total={tasks.data?.total ?? 0}
            onPageChange={(value) => {
              setTaskPage(value)
              setTaskSelection([])
            }}
          />
        </TabsContent>

        <TabsContent
          value="delivery"
          className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
        >
          <div className="flex min-h-12 flex-wrap items-center gap-2 border-b py-2">
            <span className="text-xs text-muted-foreground">
              邮箱信息会按最新密码与 MFA 状态自动选择安全凭证或邮箱访问格式
            </span>
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              {deliverySelection.length > 0 && (
                <>
                  <Button
                    disabled={copyDeliveries.isPending}
                    onClick={() =>
                      copyDeliveries.mutate({
                        copyType: "payment_links",
                        taskIds: deliverySelection,
                      })
                    }
                    size="sm"
                    variant="outline"
                  >
                    <LinkIcon />
                    已选支付链接 ({deliverySelection.length})
                  </Button>
                  <Button
                    disabled={copyDeliveries.isPending}
                    onClick={() =>
                      copyDeliveries.mutate({
                        copyType: "account_info",
                        taskIds: deliverySelection,
                      })
                    }
                    size="sm"
                    variant="outline"
                  >
                    <Mail />
                    已选邮箱信息 ({deliverySelection.length})
                  </Button>
                  <Button
                    disabled={checkPlus.isPending}
                    onClick={() =>
                      checkPlus.mutate(
                        deliveryRows
                          .filter((item) =>
                            deliverySelection.includes(item.task_id)
                          )
                          .map((item) => item.email)
                      )
                    }
                    size="sm"
                    variant="outline"
                  >
                    <ShieldCheck />
                    严格检查 Plus
                  </Button>
                </>
              )}
              <Button
                disabled={copyDeliveries.isPending}
                onClick={() =>
                  copyDeliveries.mutate({
                    all: true,
                    copyType: "payment_links",
                  })
                }
                size="sm"
              >
                <LinkIcon />
                全部支付链接
              </Button>
              <Button
                disabled={copyDeliveries.isPending}
                onClick={() =>
                  copyDeliveries.mutate({
                    all: true,
                    copyType: "account_info",
                  })
                }
                size="sm"
              >
                <Mail />
                全部邮箱信息
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
                isRefreshing={deliveries.isFetching}
                label="刷新交付信息"
                onRefresh={() => void deliveries.refetch()}
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <Table className="min-w-280">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <SelectionCheckbox
                      ids={deliveryRows
                        .filter((item) => item.deliverable)
                        .map((item) => item.task_id)}
                      selected={deliverySelection}
                      setSelected={setDeliverySelection}
                    />
                  </TableHead>
                  <TableHead>邮箱</TableHead>
                  <TableHead>支付链接</TableHead>
                  <TableHead>提取状态</TableHead>
                  <TableHead>扫码状态</TableHead>
                  <TableHead>密码</TableHead>
                  <TableHead>MFA</TableHead>
                  <TableHead>Plus</TableHead>
                  <TableHead>邮箱复制格式</TableHead>
                  <TableHead className="w-24 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deliveryRows.map((item) => (
                  <TableRow key={item.task_id}>
                    <TableCell>
                      {item.deliverable ? (
                        <RowCheckbox
                          id={item.task_id}
                          selected={deliverySelection}
                          setSelected={setDeliverySelection}
                        />
                      ) : (
                        "-"
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {item.email}
                    </TableCell>
                    <TableCell className="max-w-80">
                      {item.payment_url ? (
                        <a
                          className="block truncate font-mono text-xs text-sky-700 hover:underline dark:text-sky-300"
                          href={item.payment_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {item.payment_url}
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          尚未生成
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={item.task_status}
                        label={TASK_STATUS_LABELS[item.task_status]}
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={item.payment_status}
                        label={paymentStatusLabel(item.payment_status)}
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={item.password_status}
                        label={
                          item.password_status === "set" ? "已设置" : "未完成"
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={item.mfa_status}
                        label={
                          item.mfa_status === "enabled" ? "已启用" : "未完成"
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <PlusStateBadge
                        state={item.plus_state}
                        label={item.plus_label}
                        error={item.plus_error}
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={item.account_format}
                        label={
                          item.account_format === "security_credentials"
                            ? "安全凭证"
                            : item.account_format === "mail_access"
                              ? "邮箱访问"
                              : "不可复制"
                        }
                      />
                      {item.account_missing_reason && (
                        <span className="ml-2 text-xs text-destructive">
                          {item.account_missing_reason}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        aria-label={`复制 ${item.email} 的支付链接`}
                        disabled={!item.deliverable || copyDeliveries.isPending}
                        onClick={() =>
                          copyDeliveries.mutate({
                            copyType: "payment_links",
                            taskIds: [item.task_id],
                          })
                        }
                        size="icon-sm"
                        title="复制支付链接"
                        variant="ghost"
                      >
                        <LinkIcon />
                      </Button>
                      <Button
                        aria-label={`复制 ${item.email} 的邮箱信息`}
                        disabled={
                          !item.deliverable ||
                          item.account_format === "unavailable" ||
                          copyDeliveries.isPending
                        }
                        onClick={() =>
                          copyDeliveries.mutate({
                            copyType: "account_info",
                            taskIds: [item.task_id],
                          })
                        }
                        size="icon-sm"
                        title={item.account_missing_reason ?? "复制邮箱信息"}
                        variant="ghost"
                      >
                        <Mail />
                      </Button>
                      {item.payment_url && (
                        <Button
                          asChild
                          size="icon-sm"
                          title="打开支付链接"
                          variant="ghost"
                        >
                          <a
                            href={item.payment_url}
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
                {!deliveries.isLoading && !deliveryRows.length && (
                  <TableRow>
                    <TableCell
                      className="h-40 text-center text-sm text-muted-foreground"
                      colSpan={10}
                    >
                      本轮次暂无交付信息
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          <TablePagination
            page={deliveryPage}
            pageCount={deliveryPageCount}
            total={deliveries.data?.total ?? 0}
            onPageChange={(value) => {
              setDeliveryPage(value)
              setDeliverySelection([])
            }}
          />
        </TabsContent>

        <TabsContent
          value="cards"
          className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
        >
          <div className="flex min-h-12 items-center border-b py-2">
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              <CopySelectionBar
                selected={cardSelection}
                values={selectedCards.map((card) => card.card_code)}
                label="卡密"
                clear={() => setCardSelection([])}
              />
              <TableRefreshButton
                isRefreshing={run.isFetching}
                label="刷新卡密分配"
                onRefresh={() => void run.refetch()}
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <SelectionCheckbox
                      ids={cardRows.map((card) => card.card_id)}
                      selected={cardSelection}
                      setSelected={setCardSelection}
                    />
                  </TableHead>
                  <TableHead>卡密</TableHead>
                  <TableHead>分配统计</TableHead>
                  <TableHead>使用邮箱</TableHead>
                  <TableHead>任务 ID</TableHead>
                  <TableHead>任务状态</TableHead>
                  <TableHead>支付状态</TableHead>
                  <TableHead>扣卡</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cardRows.map((card) => (
                  <Fragment key={card.card_id}>
                    <TableRow className="bg-muted/20">
                      <TableCell>
                        <RowCheckbox
                          id={card.card_id}
                          selected={cardSelection}
                          setSelected={setCardSelection}
                        />
                      </TableCell>
                      <TableCell className="font-mono text-xs font-medium">
                        {card.card_code}
                      </TableCell>
                      <TableCell className="text-xs tabular-nums">
                        分配 {card.allocated_count} · 创建 {card.created_count}{" "}
                        · 重复 {card.duplicate_count} · 失败 {card.failed_count}
                      </TableCell>
                      <TableCell
                        colSpan={5}
                        className="text-xs text-muted-foreground"
                      >
                        {(card.assignments ?? []).length
                          ? `${card.assignments?.length} 个邮箱任务`
                          : "尚未生成 Kakao 任务"}
                      </TableCell>
                    </TableRow>
                    {(card.assignments ?? []).map((assignment) => (
                      <TableRow key={assignment.task_id}>
                        <TableCell />
                        <TableCell className="pl-6 text-xs text-muted-foreground">
                          <ChevronRight className="size-3" />
                        </TableCell>
                        <TableCell />
                        <TableCell className="font-mono text-xs">
                          {assignment.email}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {assignment.task_id}
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            status={assignment.status}
                            label={TASK_STATUS_LABELS[assignment.status]}
                          />
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            status={assignment.payment_status}
                            label={paymentStatusLabel(
                              assignment.payment_status
                            )}
                          />
                        </TableCell>
                        <TableCell>
                          {assignment.card_charged == null
                            ? "-"
                            : assignment.card_charged
                              ? "是"
                              : "否"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </Fragment>
                ))}
                {!data.cards.length && (
                  <TableRow>
                    <TableCell
                      className="h-40 text-center text-sm text-muted-foreground"
                      colSpan={8}
                    >
                      本轮次未分配卡密
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          <TablePagination
            page={cardPage}
            pageCount={cardPageCount}
            total={data.cards.length}
            onPageChange={(value) => {
              setCardPage(value)
              setCardSelection([])
            }}
          />
        </TabsContent>

        <TabsContent
          value="events"
          className="mt-3 min-h-0 flex-1 overflow-hidden border-t"
        >
          <RuntimeEventLog
            events={events.data?.items ?? []}
            loading={events.isLoading}
          />
        </TabsContent>
      </Tabs>
      <Dialog open={taskDetailOpen} onOpenChange={setTaskDetailOpen}>
        <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Kakao 任务详情</DialogTitle>
            <DialogDescription>上游返回的完整任务状态</DialogDescription>
          </DialogHeader>
          <pre className="overflow-auto rounded-sm bg-muted/40 p-3 font-mono text-xs break-all whitespace-pre-wrap">
            {JSON.stringify(taskDetail.data, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  )
}
