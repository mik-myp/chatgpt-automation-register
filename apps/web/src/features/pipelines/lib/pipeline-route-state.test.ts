import { describe, expect, it } from "vitest"

import { PipelineStatus } from "@/api/generated"
import {
  pipelineListState,
  readKakaoTaskStatus,
  readPipelineRunTab,
} from "@/features/pipelines/lib/pipeline-route-state"

describe("pipeline route state", () => {
  it("restores list filters and pagination from the URL", () => {
    const state = pipelineListState(new URLSearchParams("status=failed&page=3"))

    expect(state.status).toBe(PipelineStatus.failed)
    expect(state.page).toBe(2)
    expect(state.params).toEqual({
      status: PipelineStatus.failed,
      limit: 50,
      offset: 100,
    })
  })

  it("falls back when detail route values are invalid", () => {
    const search = new URLSearchParams(
      "tab=unknown&task_status=unknown&item_page=-2"
    )

    expect(readPipelineRunTab(search)).toBe("items")
    expect(readKakaoTaskStatus(search)).toBe("all")
    expect(pipelineListState(new URLSearchParams("page=invalid")).page).toBe(0)
  })
})
