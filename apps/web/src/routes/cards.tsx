import {
  getGetCardStatsApiKakaoCardsStatsGetQueryOptions,
  getListCardsApiKakaoCardsGetQueryOptions,
} from "@/api/generated"
import { queryClient } from "@/lib/query-client"
import { cardsRouteState } from "@/features/cards/lib/cards-route-state"
import { redirect, type LoaderFunctionArgs } from "react-router"

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url)
  const { page, pageSize, params } = cardsRouteState(url.searchParams)
  const [data] = await Promise.all([
    queryClient.ensureQueryData(getListCardsApiKakaoCardsGetQueryOptions(params)),
    queryClient.ensureQueryData(
      getGetCardStatsApiKakaoCardsStatsGetQueryOptions()
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

export { CardsPage as Component } from "@/features/cards/pages/cards-page"
