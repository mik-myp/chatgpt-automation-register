import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import * as generated from "@/api/generated"
import { useAccountsStore } from "@/stores/accounts-store"

import { BulkAccountActions } from "./accounts-page"

const mutate = vi.fn()

beforeEach(() => {
  mutate.mockReset()
  useAccountsStore.setState({
    selectedEmails: ["one@example.com", "two@example.com"],
    bulkDeleteOpen: false,
  })
  vi.spyOn(generated, "useBulkAccountActionApiAccountsBatchPost").mockReturnValue({
    mutate,
    isPending: false,
  } as never)
})

describe("BulkAccountActions", () => {
  it("submits selected accounts for password and MFA actions", async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BulkAccountActions />
      </QueryClientProvider>
    )

    await user.click(screen.getByRole("button", { name: "修改密码" }))
    expect(mutate).toHaveBeenLastCalledWith({
      data: {
        action: generated.BulkAccountAction.set_password,
        emails: ["one@example.com", "two@example.com"],
      },
    })

    await user.click(screen.getByRole("button", { name: "启用/验证 MFA" }))
    expect(mutate).toHaveBeenLastCalledWith({
      data: {
        action: generated.BulkAccountAction.enable_mfa,
        emails: ["one@example.com", "two@example.com"],
      },
    })
  })
})
