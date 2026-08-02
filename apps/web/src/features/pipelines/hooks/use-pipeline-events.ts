import { useEffect, useMemo } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey } from "@/api/generated"
import type { RuntimeEvent } from "@/components/pipelines/runtime-event-log"
import { apiRequest } from "@/lib/api-client"
import { env } from "@/lib/env"

export type PipelineEventPage = {
  items: RuntimeEvent[]
  last_sequence: number
  terminal: boolean
}

type PipelineEventStreamPayload = {
  event?: RuntimeEvent
  terminal?: boolean
}

export function usePipelineEvents(runId: string) {
  const queryClient = useQueryClient()
  const queryKey = useMemo(
    () => ["/api/pipelines/runs", runId, "events"] as const,
    [runId]
  )
  const query = useQuery({
    queryKey,
    queryFn: () =>
      apiRequest<PipelineEventPage>(
        `/api/pipelines/runs/${encodeURIComponent(runId)}/events?limit=500`
      ),
    enabled: Boolean(runId),
  })

  useEffect(() => {
    if (!runId || !query.isSuccess || query.data?.terminal) return
    const current = queryClient.getQueryData<PipelineEventPage>(queryKey)
    if (!current) return
    const baseUrl = env.VITE_API_BASE_URL.replace(/\/$/, "")
    const source = new EventSource(
      `${baseUrl}/pipelines/runs/${encodeURIComponent(runId)}/events/stream?after=${current.last_sequence}`
    )
    source.onmessage = (message) => {
      let payload: PipelineEventStreamPayload
      try {
        payload = JSON.parse(message.data) as PipelineEventStreamPayload
      } catch {
        return
      }
      queryClient.setQueryData<PipelineEventPage>(queryKey, (current) => {
        if (!current) return current
        const items = payload.event
          ? [
              ...current.items.filter(
                (item) => item.sequence !== payload.event?.sequence
              ),
              payload.event,
            ].slice(-500)
          : current.items
        return {
          items,
          last_sequence: payload.event?.sequence ?? current.last_sequence,
          terminal: Boolean(payload.terminal),
        }
      })
      void queryClient.invalidateQueries({
        queryKey: getGetPipelineRunApiPipelinesRunsRunIdGetQueryKey(runId),
      })
      if (payload.event?.event_type.startsWith("kakao_")) {
        void queryClient.invalidateQueries({ queryKey: ["/api/kakao/tasks"] })
        void queryClient.invalidateQueries({
          queryKey: ["/api/pipelines/runs", runId, "deliveries"],
        })
      }
      if (payload.terminal) source.close()
    }
    return () => source.close()
  }, [query.data?.terminal, query.isSuccess, queryClient, queryKey, runId])

  return query
}
