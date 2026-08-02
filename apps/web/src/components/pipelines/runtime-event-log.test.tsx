import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { RuntimeEventLog, type RuntimeEvent } from "./runtime-event-log"

const base: RuntimeEvent = {
  id: 1,
  sequence: 1,
  level: "error",
  event_type: "runtime_log",
  message: `https://example.com/${"continuous".repeat(30)}`,
  data: {},
  created_at: "2026-08-02T04:00:00Z",
}

describe("RuntimeEventLog", () => {
  it("renders long messages in a wrapping error row", () => {
    render(<RuntimeEventLog events={[base]} loading={false} />)
    const message = screen.getByText(base.message)
    expect(message).toHaveClass("whitespace-pre-wrap")
    expect(message).toHaveClass("[overflow-wrap:anywhere]")
    expect(message.closest(".bg-red-50\\/60")).toBeInTheDocument()
  })

  it("collapses tracebacks by default", () => {
    render(
      <RuntimeEventLog
        events={[{ ...base, event_type: "runtime_traceback", message: "stack" }]}
        loading={false}
      />
    )
    expect(screen.getByText("展开异常堆栈")).toBeInTheDocument()
    expect(screen.getByText("stack").closest("details")).not.toHaveAttribute("open")
  })
})
