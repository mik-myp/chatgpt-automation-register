import {
  KakaoTaskStatus,
  PipelineStatus,
  type ListPipelineRunsApiPipelinesRunsGetParams,
  type PipelineStatus as PipelineStatusType,
} from "@/api/generated"

export const PIPELINE_PAGE_SIZE = 50

export function readPage(searchParams: URLSearchParams, key = "page") {
  const value = Number(searchParams.get(key) ?? "1")
  return Number.isInteger(value) && value > 0 ? value - 1 : 0
}

export function pipelineListState(searchParams: URLSearchParams): {
  status: PipelineStatusType | "all"
  search: string
  page: number
  params: ListPipelineRunsApiPipelinesRunsGetParams
} {
  const requestedStatus = searchParams.get("status")
  const status = Object.values(PipelineStatus).includes(
    requestedStatus as PipelineStatusType
  )
    ? (requestedStatus as PipelineStatusType)
    : "all"
  const page = readPage(searchParams)
  const search = searchParams.get("search")?.trim() ?? ""
  return {
    status,
    search,
    page,
    params: {
      status: status === "all" ? undefined : status,
      search: search || undefined,
      limit: PIPELINE_PAGE_SIZE,
      offset: page * PIPELINE_PAGE_SIZE,
    },
  }
}

export const PIPELINE_RUN_TABS = [
  "items",
  "kakao",
  "delivery",
  "cards",
  "events",
] as const

export type PipelineRunTab = (typeof PIPELINE_RUN_TABS)[number]

export function readPipelineRunTab(
  searchParams: URLSearchParams
): PipelineRunTab {
  const value = searchParams.get("tab")
  return PIPELINE_RUN_TABS.includes(value as PipelineRunTab)
    ? (value as PipelineRunTab)
    : "items"
}

export function readKakaoTaskStatus(
  searchParams: URLSearchParams
): KakaoTaskStatus | "all" {
  const value = searchParams.get("task_status")
  return Object.values(KakaoTaskStatus).includes(value as KakaoTaskStatus)
    ? (value as KakaoTaskStatus)
    : "all"
}
