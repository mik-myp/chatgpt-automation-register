const CONTENT_MARKERS = new Set([
  "=== 卡密内容 ===",
  "=== 邮箱内容 ===",
  "=== 账号内容 ===",
])

const EXPORT_HEADERS = new Set(["卡密导出", "邮箱导出", "账号导出"])

export function normalizeImportText(text: string) {
  const lines = text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.replace(/^\ufeff/, "").trim())
  const markerIndex = lines.findIndex((line) => CONTENT_MARKERS.has(line))
  const candidates = markerIndex >= 0 ? lines.slice(markerIndex + 1) : lines

  return candidates
    .filter(
      (line) =>
        line &&
        !EXPORT_HEADERS.has(line) &&
        !line.startsWith("#") &&
        !(line.startsWith("===") && line.endsWith("==="))
    )
    .join("\n")
}

export function importEntryCount(text: string) {
  const normalized = normalizeImportText(text)
  return normalized ? normalized.split("\n").length : 0
}
