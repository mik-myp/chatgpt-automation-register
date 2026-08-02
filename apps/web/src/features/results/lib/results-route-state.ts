import {
  ListResultsApiResultsGetTokenFilter,
  type ListResultsApiResultsGetParams,
} from "@/api/generated"

const PAGE_SIZES = [25, 50, 100] as const

export function resultsRouteState(searchParams: URLSearchParams): {
  search: string
  filter: ListResultsApiResultsGetTokenFilter
  page: number
  pageSize: number
  params: ListResultsApiResultsGetParams
} {
  const search = searchParams.get("search")?.trim() ?? ""
  const requestedFilter = searchParams.get("filter")
  const filter = Object.values(ListResultsApiResultsGetTokenFilter).includes(
    requestedFilter as ListResultsApiResultsGetTokenFilter
  )
    ? (requestedFilter as ListResultsApiResultsGetTokenFilter)
    : ListResultsApiResultsGetTokenFilter.all
  const requestedPage = Number(searchParams.get("page") ?? "1")
  const page = Number.isInteger(requestedPage) && requestedPage > 0
    ? requestedPage - 1
    : 0
  const requestedPageSize = Number(searchParams.get("page_size") ?? "50")
  const pageSize = PAGE_SIZES.includes(
    requestedPageSize as (typeof PAGE_SIZES)[number]
  )
    ? requestedPageSize
    : 50
  return {
    search,
    filter,
    page,
    pageSize,
    params: {
      search: search || undefined,
      token_filter: filter,
      limit: pageSize,
      offset: page * pageSize,
    },
  }
}
