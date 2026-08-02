import type { ResultOperationSummary } from "@/api/generated"
import { apiRequest } from "@/lib/api-client"

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "canceled"])

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

export async function waitForResultOperation(
  jobId: string,
  onProgress?: (operation: ResultOperationSummary) => void
): Promise<ResultOperationSummary> {
  for (;;) {
    const operation = await apiRequest<ResultOperationSummary>(
      `/api/result-operations/${encodeURIComponent(jobId)}`
    )
    onProgress?.(operation)
    if (TERMINAL_STATUSES.has(operation.status)) return operation
    await delay(750)
  }
}

export async function runResultOperation(
  path: "/api/results/check-plus" | "/api/results/publish",
  data: object,
  onProgress?: (operation: ResultOperationSummary) => void
) {
  const operation = await apiRequest<ResultOperationSummary>(path, {
    method: "POST",
    data,
  })
  onProgress?.(operation)
  return waitForResultOperation(operation.id, onProgress)
}
