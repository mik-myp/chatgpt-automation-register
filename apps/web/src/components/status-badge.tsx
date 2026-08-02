import { Badge } from "@workspace/ui/components/badge"

const TONES: Record<string, string> = {
  success:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300",
  info: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
  warning:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  danger:
    "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  neutral: "border-border bg-muted/50 text-muted-foreground",
}

const STATUS_TONES: Record<string, keyof typeof TONES> = {
  completed: "success",
  done: "success",
  succeeded: "success",
  enabled: "success",
  set: "success",
  available: "success",
  eligible: "success",
  running: "info",
  registering: "info",
  registered: "info",
  extracting: "info",
  submitting: "info",
  in_use: "info",
  opened: "info",
  queued: "warning",
  scheduled: "warning",
  paused: "warning",
  ready: "warning",
  waiting: "warning",
  partial: "warning",
  failed: "danger",
  error: "danger",
  expired: "danger",
  skipped: "neutral",
  canceled: "neutral",
  not_set: "neutral",
  not_enabled: "neutral",
  not_requested: "neutral",
  unknown: "neutral",
}

export function StatusBadge({
  status,
  label,
  className = "",
  title,
}: {
  status?: string | null
  label?: string
  className?: string
  title?: string
}) {
  const value = status?.toLowerCase() || "unknown"
  const tone = STATUS_TONES[value] ?? "neutral"
  return (
    <Badge
      className={`${TONES[tone]} ${className}`}
      title={title}
      variant="outline"
    >
      {label ?? status ?? "未知"}
    </Badge>
  )
}
