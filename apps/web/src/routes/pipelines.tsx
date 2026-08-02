import { redirect, type LoaderFunctionArgs } from "react-router"

import { getListPipelineRunsApiPipelinesRunsGetQueryOptions } from "@/api/generated"
import {
  PIPELINE_PAGE_SIZE,
  pipelineListState,
} from "@/features/pipelines/lib/pipeline-route-state"
import { queryClient } from "@/lib/query-client"

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url)
  const { page, params } = pipelineListState(url.searchParams)
  const data = await queryClient.ensureQueryData(
    getListPipelineRunsApiPipelinesRunsGetQueryOptions(params)
  )
  const pageCount = Math.max(1, Math.ceil(data.total / PIPELINE_PAGE_SIZE))
  if (page >= pageCount) {
    if (pageCount === 1) url.searchParams.delete("page")
    else url.searchParams.set("page", String(pageCount))
    return redirect(`${url.pathname}${url.search}`)
  }
  return null
}

export { PipelinesPage as Component } from "@/features/pipelines/pages/pipelines-page"
