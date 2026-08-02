import { useState } from "react"
import { Link, useParams } from "react-router"
import { useMutation, useQuery } from "@tanstack/react-query"
import { ArrowLeft } from "lucide-react"
import { toast } from "sonner"

import {
  getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey,
  getListKakaoTasksApiKakaoTasksGetQueryKey,
  getListPipelineCardsApiPipelinesRunsRunIdCardsGetQueryKey,
  getListPipelineItemsApiPipelinesRunsRunIdItemsGetQueryKey,
  type PipelineDeliverySummary,
  PipelineRunKind,
  type ResultOperationSummary,
  useGetPipelineRunApiPipelinesRunsRunIdGet,
  useListKakaoTasksApiKakaoTasksGet,
  useListPipelineCardsApiPipelinesRunsRunIdCardsGet,
  useListPipelineItemsApiPipelinesRunsRunIdItemsGet,
} from "@/api/generated"
import { RuntimeEventLog } from "@/components/pipelines/runtime-event-log"
import { StatusBadge } from "@/components/status-badge"
import { CreateKakaoPipelineDialog } from "@/features/pipelines/components/create-kakao-dialog"
import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import { KakaoTaskDetailDialog } from "@/features/pipelines/components/kakao-task-detail-dialog"
import { KakaoTasksTab } from "@/features/pipelines/components/kakao-tasks-tab"
import { PipelineCardsTab } from "@/features/pipelines/components/pipeline-cards-tab"
import { PipelineDeliveryTab } from "@/features/pipelines/components/pipeline-delivery-tab"
import { PipelineItemsTab } from "@/features/pipelines/components/pipeline-items-tab"
import { usePipelineEvents } from "@/features/pipelines/hooks/use-pipeline-events"
import { usePipelineRunRouteState } from "@/features/pipelines/hooks/use-pipeline-run-route-state"
import {
  pipelineStatus,
  PIPELINE_KIND_LABELS,
} from "@/features/pipelines/lib/pipeline-state"
import { SecurityPipelineRunView } from "@/features/pipelines/pages/security-pipeline-run-view"
import { ApiError, apiRequest } from "@/lib/api-client"
import { runResultOperation } from "@/features/results/lib/result-operations"
import { isTerminalPaymentStatus } from "@/lib/kakao-status"
import { Button } from "@workspace/ui/components/button"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"

export function PipelineRunPage() {
  const { runId = "" } = useParams()
  const pageSize = 50
  const {
    activeTab,
    setActiveTab,
    itemPage,
    setItemPage,
    taskPage,
    setTaskPage,
    cardPage,
    setCardPage,
    deliveryPage,
    setDeliveryPage,
    taskStatus,
    setTaskStatus,
  } = usePipelineRunRouteState()
  const [itemSelection, setItemSelection] = useState<string[]>([])
  const [taskSelection, setTaskSelection] = useState<string[]>([])
  const [cardSelection, setCardSelection] = useState<string[]>([])
  const [deliverySelection, setDeliverySelection] = useState<string[]>([])
  const [taskDetailOpen, setTaskDetailOpen] = useState(false)
  const run = useGetPipelineRunApiPipelinesRunsRunIdGet(runId, {
    query: {
      queryKey: getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey(runId),
      refetchInterval: (current) => {
        if (document.visibilityState === "hidden") return false
        const status = current.state.data?.status
        return status && ["queued", "running", "paused"].includes(status)
          ? 2000
          : false
      },
    },
  })
  const events = usePipelineEvents(runId)
  const items = useListPipelineItemsApiPipelinesRunsRunIdItemsGet(
    runId,
    { limit: pageSize, offset: itemPage * pageSize },
    {
      query: {
        queryKey: getListPipelineItemsApiPipelinesRunsRunIdItemsGetQueryKey(
          runId,
          { limit: pageSize, offset: itemPage * pageSize }
        ),
        enabled: Boolean(runId),
        placeholderData: (old) => old,
      },
    }
  )
  const cards = useListPipelineCardsApiPipelinesRunsRunIdCardsGet(
    runId,
    { limit: pageSize, offset: cardPage * pageSize },
    {
      query: {
        queryKey: getListPipelineCardsApiPipelinesRunsRunIdCardsGetQueryKey(
          runId,
          { limit: pageSize, offset: cardPage * pageSize }
        ),
        enabled:
          Boolean(runId) && run.data?.kind !== PipelineRunKind.account_security,
        placeholderData: (old) => old,
      },
    }
  )
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
      refetchInterval:
        activeTab === "kakao" && document.visibilityState !== "hidden"
          ? 3000
          : false,
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
    refetchInterval:
      activeTab === "delivery" && document.visibilityState !== "hidden"
        ? 3000
        : false,
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
    refetchInterval: document.visibilityState === "hidden" ? false : 3000,
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
        pipeline_run_id: allRun ? runId : null,
      }),
    onSuccess: (result) => {
      void run.refetch()
      void items.refetch()
      void deliveries.refetch()
      toast.success(
        `Plus 检查完成：确认 Plus ${result.plus}/${result.total}${result.unknown ? `，无法确认 ${result.unknown}` : ""}`
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
      void items.refetch()
      void events.refetch()
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
        items={items}
        events={events}
        refresh={() => void run.refetch()}
        refreshing={run.isFetching}
      />
    )
  }
  const isKakao = data.kind === PipelineRunKind.kakao

  const itemRows = items.data?.items ?? []
  const cardRows = cards.data?.items ?? []
  const deliveryRows = deliveries.data?.items ?? []
  const taskRows = tasks.data?.items ?? []

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
          <div className="mt-1 flex items-center gap-1.5">
            <StatusBadge
              status={data.kind}
              label={PIPELINE_KIND_LABELS[data.kind]}
            />
            <StatusBadge {...pipelineStatus(data)} />
          </div>
        </div>
        {data.kind === PipelineRunKind.registration &&
          data.registered_count > 0 && (
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              {!data.kakao_enabled && (
                <CreateKakaoPipelineDialog sourceRunId={data.id} />
              )}
              <CreateSecurityPipelineDialog sourceRunId={data.id} />
            </div>
          )}
      </div>

      <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-5">
        {[
          ["目标", data.target_count],
          ["已调度", data.scheduled_count],
          [isKakao ? "账号完成" : "注册成功", data.registered_count],
          [isKakao ? "未创建" : "失败", data.failed_count],
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
            {isKakao ? "Kakao 账号" : "注册项"}
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
        <PipelineItemsTab
          isKakao={isKakao}
          page={itemPage}
          refresh={() => void items.refetch()}
          refreshing={items.isFetching}
          retry={(ids) => retryItems.mutate(ids)}
          retrying={retryItems.isPending}
          rows={itemRows}
          selected={itemSelection}
          setPage={setItemPage}
          setSelected={setItemSelection}
          total={items.data?.total ?? 0}
        />

        <KakaoTasksTab
          action={(action, ids) => taskAction.mutate({ action, ids })}
          detail={(id) => taskDetail.mutate(id)}
          loading={tasks.isLoading}
          page={taskPage}
          pending={taskAction.isPending}
          refresh={() => void tasks.refetch()}
          refreshing={tasks.isFetching}
          rows={taskRows}
          selected={taskSelection}
          setPage={setTaskPage}
          setSelected={setTaskSelection}
          setStatus={setTaskStatus}
          status={taskStatus}
          total={tasks.data?.total ?? 0}
        />

        <PipelineDeliveryTab
          check={(emails, allRun) => checkPlus.mutate({ emails, allRun })}
          checkPending={checkPlus.isPending}
          copy={(copyType, taskIds, all) =>
            copyDeliveries.mutate({ copyType, taskIds, all })
          }
          copyPending={copyDeliveries.isPending}
          itemTotal={items.data?.total ?? 0}
          loading={deliveries.isLoading}
          page={deliveryPage}
          refresh={() => void deliveries.refetch()}
          refreshing={deliveries.isFetching}
          rows={deliveryRows}
          selected={deliverySelection}
          setPage={setDeliveryPage}
          setSelected={setDeliverySelection}
          total={deliveries.data?.total ?? 0}
        />

        <PipelineCardsTab
          page={cardPage}
          refresh={() => void cards.refetch()}
          refreshing={cards.isFetching}
          rows={cardRows}
          selected={cardSelection}
          setPage={setCardPage}
          setSelected={setCardSelection}
          total={cards.data?.total ?? 0}
        />

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
      <KakaoTaskDetailDialog
        data={taskDetail.data}
        open={taskDetailOpen}
        onOpenChange={setTaskDetailOpen}
      />
    </div>
  )
}
