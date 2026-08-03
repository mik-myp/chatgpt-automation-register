import {
  getGetDashboardApiDashboardGetQueryOptions,
  getListPipelineRunsApiPipelinesRunsGetQueryOptions,
} from "@/api/generated"
import { DASHBOARD_RECENT_PIPELINES_PARAMS } from "@/features/dashboard/lib/dashboard-queries"
import { queryClient } from "@/lib/query-client"

export async function loader() {
  await Promise.all([
    queryClient.ensureQueryData(getGetDashboardApiDashboardGetQueryOptions()),
    queryClient.ensureQueryData(
      getListPipelineRunsApiPipelinesRunsGetQueryOptions(
        DASHBOARD_RECENT_PIPELINES_PARAMS
      )
    ),
  ])
  return null
}

export { DashboardPage as Component } from "@/features/dashboard/pages/dashboard-page"
