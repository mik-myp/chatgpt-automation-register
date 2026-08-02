import { StatusBadge } from "@/components/status-badge"

const DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
})

export type RuntimeEvent = {
  id: number
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
  return (
    <div className="divide-y text-xs" data-testid="runtime-event-log">
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
              {DATE_FORMATTER.format(new Date(event.created_at))}
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
  )
}
