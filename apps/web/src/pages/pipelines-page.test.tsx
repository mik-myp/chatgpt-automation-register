import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import MockAdapter from "axios-mock-adapter"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"

import { type PipelineRunDetail } from "@/api/generated"
import { CreateRegistrationDialog } from "@/features/pipelines/components/create-registration-dialog"
import { apiClient } from "@/lib/api-client"

import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import { SecurityPipelineRunView } from "@/features/pipelines/pages/security-pipeline-run-view"

const mock = new MockAdapter(apiClient)

afterEach(() => {
  cleanup()
  mock.reset()
})

function renderDialog(sourceRunId?: string) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })
      }
    >
      <MemoryRouter>
        <CreateSecurityPipelineDialog sourceRunId={sourceRunId} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function renderWithClient(node: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe("CreateRegistrationDialog", () => {
  it("disables creation when Kakao capacity is insufficient", async () => {
    const user = userEvent.setup()
    mock.onGet("/api/settings").reply(200, { registration: {} })
    mock.onPost("/api/kakao/cards/select").reply(409, {
      detail: "卡密实时剩余次数只有 3，无法分配 20 个任务",
    })
    renderWithClient(<CreateRegistrationDialog defaultEmail="" />)

    await user.click(screen.getByRole("button", { name: "新建注册" }))

    expect(
      await screen.findByText("卡密实时剩余次数只有 3，无法分配 20 个任务")
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "创建" })).toBeDisabled()
  })
})

describe("CreateSecurityPipelineDialog", () => {
  it("defaults a registration run's candidates to selected", async () => {
    const user = userEvent.setup()
    const items = Array.from({ length: 75 }, (_, index) => ({
      email: `candidate-${index}@example.com`,
      password_status: "not_set",
      mfa_status: "not_enabled",
      security_error: null,
      needs_password: true,
      needs_mfa: true,
    }))
    mock
      .onGet("/api/pipelines/runs/source-run/security-candidates")
      .reply(200, { items })
    renderDialog("source-run")

    await user.click(screen.getByRole("button", { name: "修改密码与 MFA" }))

    expect(
      await screen.findByRole("button", { name: "创建安全流水线（75）" })
    ).toBeEnabled()
    await user.click(screen.getByRole("button", { name: "取消" }))
  })

  it("keeps actions available while selecting a global email", async () => {
    const user = userEvent.setup()
    mock.onGet("/api/pipelines/runs/security-candidates").reply(200, {
      items: [
        {
          email: "selected@example.com",
          password_status: "not_set",
          mfa_status: "not_enabled",
          security_error: null,
          needs_password: true,
          needs_mfa: true,
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    mock.onPost("/api/pipelines/runs/security-runs").reply(201, {
      id: "security-run-id",
      kind: "account_security",
      source_pipeline_run_id: null,
      status: "queued",
      mode: "security",
      target_count: 1,
      kakao_enabled: false,
      scheduled_count: 1,
      registered_count: 0,
      failed_count: 0,
      kakao_task_count: 0,
      started_at: null,
      finished_at: null,
      created_at: "2026-08-02T00:00:00Z",
      updated_at: "2026-08-02T00:00:00Z",
    })
    renderDialog()

    await user.click(screen.getByRole("button", { name: "修改密码与 MFA" }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveClass("flex", "flex-col", "overflow-hidden")
    expect(
      screen.getByRole("button", { name: "创建安全流水线（0）" })
    ).toBeDisabled()

    await user.click(
      await screen.findByRole("checkbox", { name: "选择 selected@example.com" })
    )
    await user.click(
      screen.getByRole("button", { name: "创建安全流水线（1）" })
    )

    await waitFor(() => expect(mock.history.post).toHaveLength(1))
    expect(JSON.parse(mock.history.post[0]?.data as string)).toEqual({
      emails: ["selected@example.com"],
    })
  })
})

describe("SecurityPipelineRunView", () => {
  it("strictly checks only selected account emails", async () => {
    const user = userEvent.setup()
    const refresh = vi.fn()
    const data: PipelineRunDetail = {
      id: "security-run",
      kind: "account_security",
      source_pipeline_run_id: null,
      status: "completed",
      mode: "security",
      target_count: 2,
      kakao_enabled: false,
      scheduled_count: 2,
      registered_count: 2,
      failed_count: 0,
      kakao_task_count: 0,
      started_at: null,
      finished_at: null,
      created_at: "2026-08-02T00:00:00Z",
      updated_at: "2026-08-02T00:00:00Z",
      config_snapshot: {},
      cards: [],
      items: [
        {
          id: "item-1",
          position: 0,
          account_email: "selected@example.com",
          registration_run_id: null,
          status: "completed",
          eligibility_state: null,
          password_status: "set",
          mfa_status: "enabled",
          security_error: null,
          error: null,
          created_at: "2026-08-02T00:00:00Z",
          updated_at: "2026-08-02T00:00:00Z",
        },
        {
          id: "item-2",
          position: 1,
          account_email: "other@example.com",
          registration_run_id: null,
          status: "completed",
          eligibility_state: null,
          password_status: "set",
          mfa_status: "enabled",
          security_error: null,
          error: null,
          created_at: "2026-08-02T00:00:00Z",
          updated_at: "2026-08-02T00:00:00Z",
        },
      ],
    }
    mock.onPost("/api/results/check-plus").reply(200, {
      items: [
        {
          email: "selected@example.com",
          state: "plus",
          label: "Plus 已生效",
          is_plus: true,
          error: "",
        },
      ],
    })
    renderWithClient(
      <SecurityPipelineRunView
        data={data}
        events={{ data: { items: [] }, isLoading: false }}
        refresh={refresh}
        refreshing={false}
      />
    )

    await user.click(screen.getByRole("checkbox", { name: "选择 item-1" }))
    await user.click(screen.getByRole("button", { name: "严格检查 Plus" }))

    await waitFor(() => expect(mock.history.post).toHaveLength(1))
    expect(JSON.parse(mock.history.post[0]?.data as string)).toEqual({
      emails: ["selected@example.com"],
      all: false,
      proxy: "",
    })
    expect(refresh).toHaveBeenCalled()
  })
})
