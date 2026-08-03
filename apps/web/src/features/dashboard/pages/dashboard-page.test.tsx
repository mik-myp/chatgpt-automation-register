import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"

import * as generated from "@/api/generated"

import { DashboardPage } from "./dashboard-page"

const dashboardQuery = vi.spyOn(generated, "useGetDashboardApiDashboardGet")
const recentQuery = vi.spyOn(
  generated,
  "useListPipelineRunsApiPipelinesRunsGet"
)

const dashboard = {
  accounts: { total: 128, available: 82, in_use: 24, done: 18, failed: 4 },
  cards: { total: 36, active: 29, inactive: 7 },
  pipelines: { total: 64, active: 5, completed: 56, failed: 3 },
  jobs: { queued: 7, running: 4, failed: 2 },
  registration_results: 412,
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>
  )
}

afterEach(() => {
  cleanup()
  dashboardQuery.mockReset()
  recentQuery.mockReset()
})

describe("DashboardPage", () => {
  it("keeps the empty dashboard focused on operational data", () => {
    dashboardQuery.mockReturnValue({
      data: dashboard,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
    recentQuery.mockReturnValue({
      data: { items: [], total: 0, limit: 6, offset: 0 },
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    } as never)

    renderDashboard()

    expect(screen.getByText("暂无流水线轮次")).toBeInTheDocument()
    expect(screen.getByText("资源库存")).toBeInTheDocument()
    expect(screen.getByText("运行明细")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "新建注册" })).toBeNull()
    expect(screen.queryByText("常用入口")).toBeNull()
  })

  it("shows recent pipeline progress and inventory totals", () => {
    dashboardQuery.mockReturnValue({
      data: dashboard,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
    recentQuery.mockReturnValue({
      data: {
        items: [
          {
            id: "b4e071a9-580e-43bb-8545-81acee839a01",
            kind: "registration",
            source_pipeline_run_id: null,
            status: "running",
            mode: "batch",
            target_count: 50,
            kakao_enabled: true,
            scheduled_count: 50,
            registered_count: 32,
            failed_count: 2,
            kakao_task_count: 30,
            started_at: "2026-08-03T08:25:00Z",
            finished_at: null,
            created_at: "2026-08-03T08:24:00Z",
            updated_at: "2026-08-03T08:31:00Z",
          },
        ],
        total: 1,
        limit: 6,
        offset: 0,
      },
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    } as never)

    renderDashboard()

    expect(
      screen.getByRole("link", { name: /注册.*b4e071a9/ })
    ).toBeInTheDocument()
    expect(screen.getByText("34/50")).toBeInTheDocument()
    expect(
      screen.getByRole("link", {
        name: /邮箱.*82\/128.*使用中 24 · 完成 18 · 失败 4/,
      })
    ).toBeInTheDocument()
    expect(screen.getByText("412")).toBeInTheDocument()
  })
})
