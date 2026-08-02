export function downloadResultsJson(value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `registration-results-${new Date().toISOString().slice(0, 10)}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

export interface StrictPlusCheckResponse {
  items: Array<{
    email: string
    state: string
    label: string
    is_plus?: boolean | null
    error?: string
  }>
}
