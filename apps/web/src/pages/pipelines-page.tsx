import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  Ban,
  ChevronRight,
  Clipboard,
  ExternalLink,
  Eye,
  Inbox,
  Pause,
  Play,
  Plus,
  RefreshCw,
  X,
} from "lucide-react"
import { toast } from "sonner"

import {
  BulkPipelineAction,
  getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey,
  getListKakaoTasksApiKakaoTasksGetQueryKey,
  getListPipelineRunsApiPipelinesRunsGetQueryKey,
  KakaoTaskStatus,
  PipelineStatus,
  type PipelineStatus as PipelineStatusType,
  type PipelineRunSummary,
  useBulkPipelineActionApiPipelinesRunsBatchPost,
  useGetPipelineRunApiPipelinesRunsRunIdGet,
  useGetSettingsApiSettingsGet,
  useListKakaoTasksApiKakaoTasksGet,
  useListPipelineRunsApiPipelinesRunsGet,
} from "@/api/generated"
import { ApiError, apiRequest } from "@/lib/api-client"
import { TablePagination } from "@/components/table-pagination"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import { Switch } from "@workspace/ui/components/switch"
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
import { Textarea } from "@workspace/ui/components/textarea"

const RUN_STATUS_LABELS: Record<PipelineStatusType, string> = {
  queued: "排队中",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  canceled: "已取消",
}

const TASK_STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  extracting: "提取中",
  done: "完成",
  failed: "失败",
  canceled: "已取消",
  scheduled: "待执行",
  registering: "注册中",
  registered: "已注册",
  submitting: "提交中",
  completed: "完成",
  skipped: "跳过",
}

const DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
})

function formatDate(value: string | null) {
  return value ? DATE_FORMATTER.format(new Date(value)) : "-"
}

function SelectionCheckbox({
  ids,
  selected,
  setSelected,
}: {
  ids: string[]
  selected: string[]
  setSelected: (ids: string[]) => void
}) {
  const count = ids.filter((id) => selected.includes(id)).length
  return (
    <Checkbox
      aria-label="选择当前表格全部行"
      checked={
        ids.length > 0 && count === ids.length
          ? true
          : count > 0
            ? "indeterminate"
            : false
      }
      onCheckedChange={(checked) => setSelected(checked ? ids : [])}
    />
  )
}

function RowCheckbox({
  id,
  selected,
  setSelected,
}: {
  id: string
  selected: string[]
  setSelected: (ids: string[]) => void
}) {
  return (
    <Checkbox
      aria-label={`选择 ${id}`}
      checked={selected.includes(id)}
      onCheckedChange={() =>
        setSelected(
          selected.includes(id)
            ? selected.filter((value) => value !== id)
            : [...selected, id]
        )
      }
    />
  )
}

async function copyValues(values: string[], label: string) {
  await navigator.clipboard.writeText(values.join("\n"))
  toast.success(`已复制 ${values.length} 个${label}`)
}

function CopySelectionBar({
  selected,
  values,
  label,
  clear,
}: {
  selected: string[]
  values: string[]
  label: string
  clear: () => void
}) {
  if (!selected.length) return null
  return (
    <div className="ml-auto flex items-center justify-end gap-2">
      <span className="text-xs font-medium">已选 {selected.length} 项</span>
      <Button
        onClick={() => void copyValues(values, label)}
        size="sm"
        variant="outline"
      >
        <Clipboard />
        复制{label}
      </Button>
      <Button
        aria-label="清除选择"
        onClick={clear}
        size="icon-sm"
        variant="ghost"
      >
        <X />
      </Button>
    </div>
  )
}

type PipelineRunCreateRequest = {
  mode: "single" | "batch"
  email: string
  target_count: number
  concurrency: number | null
  otp_timeout: number | null
  proxy: string | null
  proxy_pool: string | null
  kakao_enabled: boolean
}

function CreatePipelineDialog({ defaultEmail }: { defaultEmail: string }) {
  const queryClient = useQueryClient()
  const settings = useGetSettingsApiSettingsGet()
  const [open, setOpen] = useState(Boolean(defaultEmail))
  const [mode, setMode] = useState<"single" | "batch">(
    defaultEmail ? "single" : "batch"
  )
  const [targetCount, setTargetCount] = useState(10)
  const [concurrency, setConcurrency] = useState("")
  const [otpTimeout, setOtpTimeout] = useState("")
  const [proxy, setProxy] = useState("")
  const [proxyPool, setProxyPool] = useState("")
  const [kakaoEnabled, setKakaoEnabled] = useState(true)
  const mutation = useMutation<
    PipelineRunSummary,
    ApiError,
    PipelineRunCreateRequest
  >({
    mutationFn: (data) =>
      apiRequest<PipelineRunSummary>("/api/pipelines/runs", {
        method: "POST",
        data,
      }),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({
        queryKey: ["/api/pipelines/runs"],
      })
      void queryClient.invalidateQueries({ queryKey: ["/api/dashboard"] })
      setOpen(false)
      toast.success(
        `已创建${mode === "single" ? "单次注册" : "批量轮次"} ${run.id}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const defaults = settings.data?.registration
  const numberOrNull = (value: string) => (value.trim() ? Number(value) : null)
  const textOrNull = (value: string) => value.trim() || null

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          新建注册
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>新建注册</DialogTitle>
          <DialogDescription>
            单次注册由系统自动选择邮箱，批量注册按目标数量创建流水线。
          </DialogDescription>
        </DialogHeader>

        <Tabs
          className="min-w-0"
          value={mode}
          onValueChange={(value) => setMode(value as typeof mode)}
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="single">单次注册</TabsTrigger>
            <TabsTrigger value="batch">批量流水线</TabsTrigger>
          </TabsList>
          <TabsContent className="mt-4" value="single">
            <div className="border-y py-4 text-sm text-muted-foreground">
              Outlook 模式从号池领取一个可用账号；Cloudflare
              模式自动创建临时邮箱。
            </div>
          </TabsContent>
          <TabsContent className="mt-4 space-y-5" value="batch">
            <section className="grid gap-4 border-y py-4 sm:grid-cols-3">
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                目标数量
                <Input
                  max={10000}
                  min={1}
                  onChange={(event) =>
                    setTargetCount(Math.max(1, Number(event.target.value)))
                  }
                  type="number"
                  value={targetCount}
                />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                并发数
                <Input
                  max={50}
                  min={1}
                  onChange={(event) => setConcurrency(event.target.value)}
                  placeholder={`系统设置：${defaults?.concurrency ?? 10}`}
                  type="number"
                  value={concurrency}
                />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                OTP 超时（秒）
                <Input
                  max={300}
                  min={1}
                  onChange={(event) => setOtpTimeout(event.target.value)}
                  placeholder={`系统设置：${defaults?.otp_timeout ?? 10}`}
                  type="number"
                  value={otpTimeout}
                />
              </label>
            </section>
            <section className="grid gap-4">
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                固定代理
                <Input
                  onChange={(event) => setProxy(event.target.value)}
                  placeholder={defaults?.proxy || "系统设置：直连"}
                  value={proxy}
                />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                代理池（每行一个）
                <Textarea
                  className="min-h-28 resize-y font-mono text-xs"
                  onChange={(event) => setProxyPool(event.target.value)}
                  placeholder={
                    defaults?.proxy_pool
                      ? "留空使用系统代理池"
                      : "留空使用系统设置"
                  }
                  value={proxyPool}
                />
              </label>
            </section>
          </TabsContent>
        </Tabs>

        <label className="flex items-center justify-between border-y py-3 text-sm">
          <span>创建 Kakao Pay 任务</span>
          <Switch checked={kakaoEnabled} onCheckedChange={setKakaoEnabled} />
        </label>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate({
                mode,
                email: "",
                target_count: mode === "single" ? 1 : targetCount,
                concurrency:
                  mode === "batch" ? numberOrNull(concurrency) : null,
                otp_timeout: mode === "batch" ? numberOrNull(otpTimeout) : null,
                proxy: mode === "batch" ? textOrNull(proxy) : null,
                proxy_pool: mode === "batch" ? textOrNull(proxyPool) : null,
                kakao_enabled: kakaoEnabled,
              })
            }
          >
            <Plus />
            {mutation.isPending ? "正在创建" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function PipelinesPage() {
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<PipelineStatusType | "all">("all")
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const pageSize = 50
  const params = {
    status: status === "all" ? undefined : status,
    limit: pageSize,
    offset: page * pageSize,
  }
  const query = useListPipelineRunsApiPipelinesRunsGet(params, {
    query: {
      queryKey: getListPipelineRunsApiPipelinesRunsGetQueryKey(params),
      refetchInterval: 2000,
    },
  })
  const mutation = useBulkPipelineActionApiPipelinesRunsBatchPost<ApiError>({
    mutation: {
      onSuccess: (result, variables) => {
        void queryClient.invalidateQueries({
          queryKey: ["/api/pipelines/runs"],
        })
        setSelected([])
        const skipped = result.skipped ? `，跳过 ${result.skipped}` : ""
        const labels = {
          [BulkPipelineAction.cancel]: "取消",
          [BulkPipelineAction.pause]: "暂停",
          [BulkPipelineAction.resume]: "恢复",
        }
        toast.success(
          `${labels[variables.data.action]}完成：处理 ${result.processed}${skipped}`
        )
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const rows = query.data?.items ?? []
  const total = query.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">流水线轮次</h1>
        <CreatePipelineDialog defaultEmail={searchParams.get("email") ?? ""} />
      </div>

      <section
        className="flex min-h-0 min-w-0 flex-1 flex-col border-t"
        aria-label="流水线轮次列表"
      >
        <div className="flex flex-wrap items-center gap-2 border-b py-3">
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value as typeof status)
              setPage(0)
              setSelected([])
            }}
          >
            <SelectTrigger aria-label="轮次状态" className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              {Object.entries(RUN_STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selected.length > 0 && (
            <div className="ml-auto flex items-center justify-end gap-2">
              <span className="text-xs font-medium">
                已选 {selected.length} 项
              </span>
              <Button
                disabled={mutation.isPending}
                onClick={() =>
                  mutation.mutate({
                    data: {
                      action: BulkPipelineAction.pause,
                      run_ids: selected,
                    },
                  })
                }
                size="sm"
                variant="outline"
              >
                <Pause />
                暂停
              </Button>
              <Button
                disabled={mutation.isPending}
                onClick={() =>
                  mutation.mutate({
                    data: {
                      action: BulkPipelineAction.resume,
                      run_ids: selected,
                    },
                  })
                }
                size="sm"
                variant="outline"
              >
                <Play />
                恢复
              </Button>
              <Button
                disabled={mutation.isPending}
                onClick={() =>
                  mutation.mutate({
                    data: {
                      action: BulkPipelineAction.cancel,
                      run_ids: selected,
                    },
                  })
                }
                size="sm"
                variant="outline"
              >
                <Ban />
                取消轮次
              </Button>
              <Button
                aria-label="清除选择"
                onClick={() => setSelected([])}
                size="icon-sm"
                variant="ghost"
              >
                <X />
              </Button>
            </div>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Table className="min-w-190">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <SelectionCheckbox
                    ids={rows.map((row) => row.id)}
                    selected={selected}
                    setSelected={setSelected}
                  />
                </TableHead>
                <TableHead>轮次</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>目标</TableHead>
                <TableHead>注册成功</TableHead>
                <TableHead>Kakao 任务</TableHead>
                <TableHead>开始时间</TableHead>
                <TableHead className="w-32 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>
                    <RowCheckbox
                      id={run.id}
                      selected={selected}
                      setSelected={setSelected}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <Link
                      className="hover:underline"
                      to={`/pipelines/${run.id}`}
                    >
                      {run.id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {RUN_STATUS_LABELS[run.status]}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {run.target_count}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {run.registered_count}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {run.kakao_task_count}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatDate(run.started_at ?? run.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    {(run.status === PipelineStatus.queued ||
                      run.status === PipelineStatus.running) && (
                      <Button
                        aria-label={`暂停轮次 ${run.id}`}
                        disabled={mutation.isPending}
                        onClick={() =>
                          mutation.mutate({
                            data: {
                              action: BulkPipelineAction.pause,
                              run_ids: [run.id],
                            },
                          })
                        }
                        size="icon-sm"
                        title="暂停"
                        variant="ghost"
                      >
                        <Pause />
                      </Button>
                    )}
                    {run.status === PipelineStatus.paused && (
                      <Button
                        aria-label={`恢复轮次 ${run.id}`}
                        disabled={mutation.isPending}
                        onClick={() =>
                          mutation.mutate({
                            data: {
                              action: BulkPipelineAction.resume,
                              run_ids: [run.id],
                            },
                          })
                        }
                        size="icon-sm"
                        title="恢复"
                        variant="ghost"
                      >
                        <Play />
                      </Button>
                    )}
                    {(run.status === PipelineStatus.queued ||
                      run.status === PipelineStatus.running ||
                      run.status === PipelineStatus.paused) && (
                      <Button
                        aria-label={`取消轮次 ${run.id}`}
                        disabled={mutation.isPending}
                        onClick={() =>
                          mutation.mutate({
                            data: {
                              action: BulkPipelineAction.cancel,
                              run_ids: [run.id],
                            },
                          })
                        }
                        size="icon-sm"
                        title="取消"
                        variant="ghost"
                      >
                        <Ban />
                      </Button>
                    )}
                    <Button
                      asChild
                      aria-label={`查看轮次 ${run.id}`}
                      size="icon-sm"
                      variant="ghost"
                    >
                      <Link to={`/pipelines/${run.id}`}>
                        <ChevronRight />
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!query.isLoading && !rows.length && (
                <TableRow>
                  <TableCell className="h-52 text-center" colSpan={8}>
                    <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                    <p className="text-sm font-medium">暂无流水线轮次</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <TablePagination
          page={page}
          pageCount={pageCount}
          onPageChange={(value) => {
            setPage(value)
            setSelected([])
          }}
        />
      </section>
    </div>
  )
}

export function PipelineRunPage() {
  const { runId = "" } = useParams()
  const pageSize = 50
  const [itemPage, setItemPage] = useState(0)
  const [taskPage, setTaskPage] = useState(0)
  const [cardPage, setCardPage] = useState(0)
  const [itemSelection, setItemSelection] = useState<string[]>([])
  const [taskSelection, setTaskSelection] = useState<string[]>([])
  const [cardSelection, setCardSelection] = useState<string[]>([])
  const [taskStatus, setTaskStatus] = useState<KakaoTaskStatus | "all">("all")
  const [taskDetailOpen, setTaskDetailOpen] = useState(false)
  const run = useGetPipelineRunApiPipelinesRunsRunIdGet(runId, {
    query: {
      queryKey: getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey(runId),
      refetchInterval: 2000,
    },
  })
  const activeRun =
    run.data?.status === PipelineStatus.queued ||
    run.data?.status === PipelineStatus.running ||
    run.data?.status === PipelineStatus.paused
  const events = useQuery({
    queryKey: ["/api/pipelines/runs", runId, "events"],
    queryFn: () =>
      apiRequest<{
        items: Array<{
          id: number
          sequence: number
          level: string
          event_type: string
          message: string
          data: Record<string, unknown>
          created_at: string
        }>
        last_sequence: number
        terminal: boolean
      }>(`/api/pipelines/runs/${encodeURIComponent(runId)}/events?limit=500`),
    enabled: Boolean(runId) && activeRun,
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
      enabled: Boolean(runId),
    },
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

  const selectedItems = data.items.filter((item) =>
    itemSelection.includes(item.id)
  )
  const selectedTasks = (tasks.data?.items ?? []).filter((task) =>
    taskSelection.includes(task.id)
  )
  const selectedCards = data.cards.filter((card) =>
    cardSelection.includes(card.card_id)
  )
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
          <Badge className="mt-1" variant="outline">
            {RUN_STATUS_LABELS[data.status]}
          </Badge>
        </div>
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

      <Tabs className="flex min-h-0 flex-1 flex-col" defaultValue="items">
        <TabsList>
          <TabsTrigger value="items">注册项</TabsTrigger>
          <TabsTrigger value="kakao">Kakao 任务</TabsTrigger>
          <TabsTrigger value="cards">卡密分配</TabsTrigger>
          {activeRun && <TabsTrigger value="events">实时日志</TabsTrigger>}
        </TabsList>
        <TabsContent
          value="items"
          className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
        >
          <div className="flex min-h-12 items-center border-b py-2">
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
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <Table>
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
                      <Badge variant="outline">
                        {TASK_STATUS_LABELS[item.status]}
                      </Badge>
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
                className="w-32"
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
                      <Badge variant="outline">
                        {TASK_STATUS_LABELS[task.status]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {task.payment_status ?? "-"}
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
            onPageChange={(value) => {
              setTaskPage(value)
              setTaskSelection([])
            }}
          />
        </TabsContent>

        <TabsContent
          value="cards"
          className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
        >
          <div className="flex min-h-12 items-center border-b py-2">
            <CopySelectionBar
              selected={cardSelection}
              values={selectedCards.map((card) => card.card_id)}
              label="卡密 ID"
              clear={() => setCardSelection([])}
            />
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
                  <TableHead>分配</TableHead>
                  <TableHead>创建</TableHead>
                  <TableHead>重复</TableHead>
                  <TableHead>失败</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cardRows.map((card) => (
                  <TableRow key={card.card_id}>
                    <TableCell>
                      <RowCheckbox
                        id={card.card_id}
                        selected={cardSelection}
                        setSelected={setCardSelection}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {card.card_hint}
                    </TableCell>
                    <TableCell>{card.allocated_count}</TableCell>
                    <TableCell>{card.created_count}</TableCell>
                    <TableCell>{card.duplicate_count}</TableCell>
                    <TableCell>{card.failed_count}</TableCell>
                  </TableRow>
                ))}
                {!data.cards.length && (
                  <TableRow>
                    <TableCell
                      className="h-40 text-center text-sm text-muted-foreground"
                      colSpan={6}
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
            onPageChange={(value) => {
              setCardPage(value)
              setCardSelection([])
            }}
          />
        </TabsContent>

        {activeRun && (
          <TabsContent
            value="events"
            className="mt-3 min-h-0 flex-1 overflow-auto border-t"
          >
            <div className="divide-y font-mono text-xs">
              {(events.data?.items ?? []).map((event) => (
                <div
                  className="grid grid-cols-[72px_80px_minmax(0,1fr)] gap-3 px-2 py-2"
                  key={event.id}
                >
                  <span className="text-muted-foreground">
                    {DATE_FORMATTER.format(new Date(event.created_at))}
                  </span>
                  <span
                    className={
                      event.level === "error"
                        ? "text-destructive"
                        : "text-muted-foreground"
                    }
                  >
                    {event.event_type}
                  </span>
                  <span className="whitespace-pre-wrap">{event.message}</span>
                </div>
              ))}
              {!events.isLoading && !events.data?.items.length && (
                <div className="py-16 text-center text-muted-foreground">
                  暂无运行日志
                </div>
              )}
            </div>
          </TabsContent>
        )}
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
