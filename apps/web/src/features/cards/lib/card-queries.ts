import { type QueryClient } from "@tanstack/react-query"

export function refreshCardQueries(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    predicate: (query) =>
      typeof query.queryKey[0] === "string" &&
      query.queryKey[0].startsWith("/api/kakao/cards"),
  })
}
