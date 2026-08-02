import { useCallback } from "react"
import { useSearchParams } from "react-router"

import {
  readKakaoTaskStatus,
  readPage,
  readPipelineRunTab,
  type PipelineRunTab,
} from "@/features/pipelines/lib/pipeline-route-state"

export function usePipelineRunRouteState() {
  const [searchParams, setSearchParams] = useSearchParams()

  const setValue = useCallback(
    (key: string, value: string, defaultValue?: string) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          if (!value || value === defaultValue) next.delete(key)
          else next.set(key, value)
          return next
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  const setPage = useCallback(
    (key: string, page: number) => setValue(key, String(page + 1), "1"),
    [setValue]
  )

  return {
    activeTab: readPipelineRunTab(searchParams),
    setActiveTab: (value: string) =>
      setValue("tab", value as PipelineRunTab, "items"),
    itemPage: readPage(searchParams, "item_page"),
    setItemPage: (page: number) => setPage("item_page", page),
    taskPage: readPage(searchParams, "task_page"),
    setTaskPage: (page: number) => setPage("task_page", page),
    cardPage: readPage(searchParams, "card_page"),
    setCardPage: (page: number) => setPage("card_page", page),
    deliveryPage: readPage(searchParams, "delivery_page"),
    setDeliveryPage: (page: number) => setPage("delivery_page", page),
    taskStatus: readKakaoTaskStatus(searchParams),
    setTaskStatus: (value: string) => setValue("task_status", value, "all"),
  }
}
