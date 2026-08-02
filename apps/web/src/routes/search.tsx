import { type LoaderFunctionArgs } from "react-router"

import {
  getListAccountsApiAccountsGetQueryOptions,
  getListPipelineRunsApiPipelinesRunsGetQueryOptions,
} from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader({ request }: LoaderFunctionArgs) {
  const query = new URL(request.url).searchParams.get("q")?.trim() ?? ""
  if (!query) return null
  await Promise.all([
    queryClient.ensureQueryData(
      getListAccountsApiAccountsGetQueryOptions({
        search: query,
        limit: 20,
        offset: 0,
      })
    ),
    queryClient.ensureQueryData(
      getListPipelineRunsApiPipelinesRunsGetQueryOptions({
        search: query,
        limit: 20,
        offset: 0,
      })
    ),
  ])
  return null
}

export { SearchPage as Component } from "@/features/search/pages/search-page"
