import {
  getGetCardStatsApiKakaoCardsStatsGetQueryOptions,
  getListCardsApiKakaoCardsGetQueryOptions,
} from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader() {
  await Promise.all([
    queryClient.ensureQueryData(
      getListCardsApiKakaoCardsGetQueryOptions({ limit: 50, offset: 0 })
    ),
    queryClient.ensureQueryData(
      getGetCardStatsApiKakaoCardsStatsGetQueryOptions()
    ),
  ])
  return null
}

export { CardsPage as Component } from "@/features/cards/pages/cards-page"
