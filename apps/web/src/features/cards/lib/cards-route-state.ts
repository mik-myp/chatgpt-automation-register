import type { ListCardsApiKakaoCardsGetParams } from "@/api/generated"

const PAGE_SIZES = [25, 50, 100] as const

export function cardsRouteState(searchParams: URLSearchParams): {
  search: string
  state: "all" | "active" | "inactive"
  page: number
  pageSize: number
  params: ListCardsApiKakaoCardsGetParams
} {
  const search = searchParams.get("search")?.trim() ?? ""
  const requestedState = searchParams.get("state")
  const state =
    requestedState === "active" || requestedState === "inactive"
      ? requestedState
      : "all"
  const requestedPage = Number(searchParams.get("page") ?? "1")
  const page =
    Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage - 1 : 0
  const requestedPageSize = Number(searchParams.get("page_size") ?? "50")
  const pageSize = PAGE_SIZES.includes(
    requestedPageSize as (typeof PAGE_SIZES)[number]
  )
    ? requestedPageSize
    : 50
  return {
    search,
    state,
    page,
    pageSize,
    params: {
      search: search || undefined,
      active: state === "all" ? undefined : state === "active",
      limit: pageSize,
      offset: page * pageSize,
    },
  }
}
