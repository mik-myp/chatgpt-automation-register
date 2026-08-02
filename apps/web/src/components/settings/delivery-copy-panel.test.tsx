import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { type DeliveryCopySettings } from "@/api/generated"

import { DeliveryCopyPanel } from "./delivery-copy-panel"

afterEach(cleanup)

describe("DeliveryCopyPanel", () => {
  it("maps the Plus-only switch to delivery copy settings", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const value: DeliveryCopySettings = {}
    render(<DeliveryCopyPanel value={value} onChange={onChange} />)

    await user.click(
      screen.getByRole("switch", {
        name: "仅复制确认是 Plus 的邮箱",
      })
    )

    expect(onChange).toHaveBeenCalledWith({ only_copy_plus: true })
  })
})
