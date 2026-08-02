import {
  AccountStatus,
  type AccountStatus as AccountStatusType,
  type ListAccountsApiAccountsGetParams,
} from "@/api/generated"

const PAGE_SIZES = [25, 50, 100] as const

export function accountsRouteState(searchParams: URLSearchParams): {
  search: string
  status: AccountStatusType | "all"
  page: number
  pageSize: number
  params: ListAccountsApiAccountsGetParams
} {
  const search = searchParams.get("search")?.trim() ?? ""
  const requestedStatus = searchParams.get("status")
  const status = Object.values(AccountStatus).includes(
    requestedStatus as AccountStatusType
  )
    ? (requestedStatus as AccountStatusType)
    : "all"
  const requestedPage = Number(searchParams.get("page") ?? "1")
  const page = Number.isInteger(requestedPage) && requestedPage > 0
    ? requestedPage - 1
    : 0
  const requestedPageSize = Number(searchParams.get("page_size") ?? "25")
  const pageSize = PAGE_SIZES.includes(
    requestedPageSize as (typeof PAGE_SIZES)[number]
  )
    ? requestedPageSize
    : 25
  return {
    search,
    status,
    page,
    pageSize,
    params: {
      search: search || undefined,
      status: status === "all" ? undefined : status,
      limit: pageSize,
      offset: page * pageSize,
    },
  }
}
