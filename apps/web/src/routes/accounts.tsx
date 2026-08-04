import {
  getGetAccountStatsApiAccountsStatsGetQueryOptions,
  getListAccountsApiAccountsGetQueryOptions,
} from "@/api/generated"
import { queryClient } from "@/lib/query-client"
import { accountsRouteState } from "@/features/accounts/lib/accounts-route-state"
import { redirect, type LoaderFunctionArgs } from "react-router"

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url)
  const { page, pageSize, params } = accountsRouteState(url.searchParams)
  const [data] = await Promise.all([
    queryClient.ensureQueryData(
      getListAccountsApiAccountsGetQueryOptions(params)
    ),
    queryClient.ensureQueryData(
      getGetAccountStatsApiAccountsStatsGetQueryOptions()
    ),
  ])
  const pageCount = Math.max(1, Math.ceil(data.total / pageSize))
  if (page >= pageCount) {
    if (pageCount === 1) url.searchParams.delete("page")
    else url.searchParams.set("page", String(pageCount))
    return redirect(`${url.pathname}${url.search}`)
  }
  return null
}

export { AccountsPage as Component } from "@/features/accounts/pages/accounts-page"
