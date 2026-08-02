import type { LoaderFunctionArgs } from "react-router"

import { getGetPipelineRunApiPipelinesRunsRunIdGetQueryOptions } from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader({ params }: LoaderFunctionArgs) {
  const runId = params.runId ?? ""
  await queryClient.ensureQueryData(
    getGetPipelineRunApiPipelinesRunsRunIdGetQueryOptions(runId)
  )
  return null
}

export { PipelineRunPage as Component } from "@/features/pipelines/pages/pipeline-run-page"
