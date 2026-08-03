import {
  useGetDashboardApiDashboardGet,
  useListPipelineRunsApiPipelinesRunsGet,
} from "@/api/generated"
import { TableRefreshButton } from "@/components/table-refresh-button"
import { DashboardResources } from "@/features/dashboard/components/dashboard-resources"
import { DashboardStatusStrip } from "@/features/dashboard/components/dashboard-status-strip"
import { RecentPipelines } from "@/features/dashboard/components/recent-pipelines"
import { DASHBOARD_RECENT_PIPELINES_PARAMS } from "@/features/dashboard/lib/dashboard-queries"

export function DashboardPage() {
  const dashboard = useGetDashboardApiDashboardGet()
  const recent = useListPipelineRunsApiPipelinesRunsGet(
    DASHBOARD_RECENT_PIPELINES_PARAMS
  )
  const data = dashboard.data
  const refreshing = dashboard.isFetching || recent.isFetching
  const refresh = () => {
    void dashboard.refetch()
    void recent.refetch()
  }

  if (!data) return null

  return (
    <div className="h-full min-h-0 overflow-auto">
      <div className="mx-auto flex min-h-full w-full max-w-360 flex-col gap-6 pb-2">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">工作台</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              本地资源与流水线运行概览
            </p>
          </div>
          <TableRefreshButton
            isRefreshing={refreshing}
            label="刷新工作台"
            onRefresh={refresh}
          />
        </header>

        <DashboardStatusStrip data={data} />

        <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[minmax(0,1fr)_20rem]">
          <RecentPipelines
            error={recent.isError}
            loading={recent.isLoading}
            runs={recent.data?.items ?? []}
          />
          <DashboardResources data={data} />
        </div>
      </div>
    </div>
  )
}
