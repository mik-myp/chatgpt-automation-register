const BEIJING_TIME_ZONE = "Asia/Shanghai"
const TIME_ZONE_SUFFIX = /(Z|[+-]\d{2}:?\d{2})$/i

const FULL_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
})

const COMPACT_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
})

function parseApiDateTime(value: string) {
  const trimmed = value.trim()
  // SQLite strips timezone metadata from UTC timestamps returned by the API.
  return new Date(TIME_ZONE_SUFFIX.test(trimmed) ? trimmed : `${trimmed}Z`)
}

function format(
  value: string | null | undefined,
  formatter: Intl.DateTimeFormat
) {
  if (!value) return "-"
  const date = parseApiDateTime(value)
  return Number.isNaN(date.getTime()) ? "-" : formatter.format(date)
}

export function formatBeijingDateTime(value: string | null | undefined) {
  return format(value, FULL_DATE_TIME_FORMATTER)
}

export function formatCompactBeijingDateTime(value: string | null | undefined) {
  return format(value, COMPACT_DATE_TIME_FORMATTER)
}
