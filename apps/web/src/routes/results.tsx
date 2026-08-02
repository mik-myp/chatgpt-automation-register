import {
  getListResultsApiResultsGetQueryOptions,
  ListResultsApiResultsGetTokenFilter,
} from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader() {
  await queryClient.ensureQueryData(
    getListResultsApiResultsGetQueryOptions({
      token_filter: ListResultsApiResultsGetTokenFilter.all,
      limit: 50,
      offset: 0,
    })
  )
  return null
}

export { ResultsPage as Component } from "@/features/results/pages/results-page"
