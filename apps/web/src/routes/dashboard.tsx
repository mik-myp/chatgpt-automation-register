import { getGetDashboardApiDashboardGetQueryOptions } from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader() {
  await queryClient.ensureQueryData(
    getGetDashboardApiDashboardGetQueryOptions()
  )
  return null
}

export { DashboardPage as Component } from "@/features/dashboard/pages/dashboard-page"
