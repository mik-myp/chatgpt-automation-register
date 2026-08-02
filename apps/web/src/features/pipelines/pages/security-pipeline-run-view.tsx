import { Link } from "react-router"
import { ArrowLeft } from "lucide-react"

import {
  type PipelineItemListResponse,
  type PipelineRunDetail,
} from "@/api/generated"
import {
  RuntimeEventLog,
  type RuntimeEvent,
} from "@/components/pipelines/runtime-event-log"
import { StatusBadge } from "@/components/status-badge"
import { SecurityAccountsTab } from "@/features/pipelines/components/security-accounts-tab"
import { usePipelineRunRouteState } from "@/features/pipelines/hooks/use-pipeline-run-route-state"
import { pipelineStatus } from "@/features/pipelines/lib/pipeline-state"
import { Button } from "@workspace/ui/components/button"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"

export function SecurityPipelineRunView({
  data,
  items,
  events,
  refresh,
  refreshing,
}: {
  data: PipelineRunDetail
  items: {
    data?: PipelineItemListResponse
    isLoading: boolean
    isFetching: boolean
    refetch: () => Promise<unknown>
  }
  events: {
    data?: { items: RuntimeEvent[] }
    isLoading: boolean
    refetch: () => Promise<unknown>
  }
  refresh: () => void
  refreshing: boolean
}) {
  const routeState = usePipelineRunRouteState()
  const activeTab = routeState.activeTab === "events" ? "events" : "items"

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
            Math.max(
              0,
              data.target_count - data.registered_count - data.failed_count
            ),
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
        <SecurityAccountsTab
          data={data}
          items={items}
          events={events}
          refresh={refresh}
          refreshing={refreshing}
        />
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
