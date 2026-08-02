import {
  getGetAccountStatsApiAccountsStatsGetQueryOptions,
  getListAccountsApiAccountsGetQueryOptions,
} from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader() {
  await Promise.all([
    queryClient.ensureQueryData(
      getListAccountsApiAccountsGetQueryOptions({ limit: 25, offset: 0 })
    ),
    queryClient.ensureQueryData(
      getGetAccountStatsApiAccountsStatsGetQueryOptions()
    ),
  ])
  return null
}

export { AccountsPage as Component } from "@/features/accounts/pages/accounts-page"
