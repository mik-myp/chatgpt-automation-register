import { getListResultsApiResultsGetQueryOptions } from "@/api/generated"
import { queryClient } from "@/lib/query-client"
import { resultsRouteState } from "@/features/results/lib/results-route-state"
import { redirect, type LoaderFunctionArgs } from "react-router"

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url)
  const { page, pageSize, params } = resultsRouteState(url.searchParams)
  const data = await queryClient.ensureQueryData(
    getListResultsApiResultsGetQueryOptions(params)
  )
  const pageCount = Math.max(1, Math.ceil(data.total / pageSize))
  if (page >= pageCount) {
    if (pageCount === 1) url.searchParams.delete("page")
    else url.searchParams.set("page", String(pageCount))
    return redirect(`${url.pathname}${url.search}`)
  }
  return null
}

export { ResultsPage as Component } from "@/features/results/pages/results-page"
