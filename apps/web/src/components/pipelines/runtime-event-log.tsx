import { useEffect, useRef, useState } from "react"

import { StatusBadge } from "@/components/status-badge"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { Switch } from "@workspace/ui/components/switch"

export type RuntimeEvent = {
  id: number
  cursor: number
  sequence: number
  level: string
  event_type: string
  message: string
  data: Record<string, unknown>
  created_at: string
}

export function RuntimeEventLog({
  events,
  loading,
}: {
  events: RuntimeEvent[]
  loading: boolean
}) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const lastSequence = events.at(-1)?.sequence ?? 0

  useEffect(() => {
    const viewport = viewportRef.current
    if (!autoScroll || !viewport) return
    viewport.scrollTop = viewport.scrollHeight
  }, [autoScroll, lastSequence])

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="runtime-event-log">
      <div className="flex h-11 shrink-0 items-center justify-end gap-2 border-b px-3 text-xs">
        <span className="text-muted-foreground">自动滚动</span>
        <Switch
          aria-label="自动滚动"
          checked={autoScroll}
          onCheckedChange={setAutoScroll}
        />
      </div>
      <div
        className="min-h-0 flex-1 divide-y overflow-auto text-xs"
        data-testid="runtime-event-viewport"
        onScroll={(event) => {
          if (!autoScroll) return
          const viewport = event.currentTarget
          const distance = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
          if (distance > 80) setAutoScroll(false)
        }}
        ref={viewportRef}
      >
        {events.map((event) => (
          <div
            className={
              event.level === "error"
                ? "bg-red-50/60 px-3 py-3 dark:bg-red-950/20"
                : event.level === "warning"
                  ? "bg-amber-50/60 px-3 py-3 dark:bg-amber-950/20"
                  : "px-3 py-3"
            }
            key={event.id}
          >
            <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2">
              <span className="font-mono text-muted-foreground tabular-nums">
                {formatCompactBeijingDateTime(event.created_at)}
              </span>
              <StatusBadge
                status={event.level}
                label={
                  {
                    error: "错误",
                    warning: "警告",
                    info: "信息",
                    debug: "调试",
                  }[event.level] ?? event.level
                }
              />
              <span className="min-w-0 break-all font-mono font-medium">
                {event.event_type}
              </span>
            </div>
            {event.event_type === "runtime_traceback" ? (
              <details>
                <summary className="cursor-pointer text-muted-foreground">
                  展开异常堆栈
                </summary>
                <pre className="mt-2 max-w-full overflow-x-auto whitespace-pre-wrap font-mono leading-5 [overflow-wrap:anywhere]">
                  {event.message}
                </pre>
              </details>
            ) : (
              <div className="max-w-full whitespace-pre-wrap font-mono leading-5 [overflow-wrap:anywhere]">
                {event.message}
              </div>
            )}
          </div>
        ))}
        {!loading && !events.length && (
          <div className="py-16 text-center text-muted-foreground">暂无运行日志</div>
        )}
      </div>
    </div>
  )
}
