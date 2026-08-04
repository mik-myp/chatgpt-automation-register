import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { RuntimeEventLog, type RuntimeEvent } from "./runtime-event-log"

const base: RuntimeEvent = {
  id: 1,
  cursor: 1,
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
        events={[
          { ...base, event_type: "runtime_traceback", message: "stack" },
        ]}
        loading={false}
      />
    )
    expect(screen.getByText("展开异常堆栈")).toBeInTheDocument()
    expect(screen.getByText("stack").closest("details")).not.toHaveAttribute(
      "open"
    )
  })

  it("auto scrolls for new events and pauses after manual scrolling", () => {
    const view = render(<RuntimeEventLog events={[base]} loading={false} />)
    const viewport = view.container.querySelector<HTMLElement>(
      '[data-testid="runtime-event-viewport"]'
    )
    expect(viewport).not.toBeNull()
    if (!viewport) return
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 200 },
    })

    view.rerender(
      <RuntimeEventLog
        events={[base, { ...base, id: 2, sequence: 2 }]}
        loading={false}
      />
    )
    expect(viewport.scrollTop).toBe(1000)

    viewport.scrollTop = 100
    fireEvent.scroll(viewport)
    expect(view.container.querySelector('[role="switch"]')).not.toBeChecked()
  })
})
