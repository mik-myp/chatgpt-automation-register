import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import * as generated from "@/api/generated"
import { useAccountsStore } from "@/stores/accounts-store"

import { BulkAccountActions } from "@/features/accounts/components/account-tools"

const mutate = vi.fn()

beforeEach(() => {
  mutate.mockReset()
  useAccountsStore.setState({
    selectedEmails: ["one@example.com", "two@example.com"],
    bulkDeleteOpen: false,
  })
  vi.spyOn(
    generated,
    "useBulkAccountActionApiAccountsBatchPost"
  ).mockReturnValue({
    mutate,
    isPending: false,
  } as never)
})

describe("BulkAccountActions", () => {
  it("keeps account pool actions separate from security actions", async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BulkAccountActions />
      </QueryClientProvider>
    )

    expect(screen.queryByRole("button", { name: "修改密码" })).toBeNull()
    expect(screen.queryByRole("button", { name: "启用/验证 MFA" })).toBeNull()

    await user.click(screen.getByRole("button", { name: "释放" }))
    expect(mutate).toHaveBeenLastCalledWith({
      data: {
        action: generated.BulkAccountAction.release,
        emails: ["one@example.com", "two@example.com"],
      },
    })
  })
})
