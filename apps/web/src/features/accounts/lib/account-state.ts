import { AccountStatus } from "@/api/generated"
import { ApiError } from "@/lib/api-client"

export const ACCOUNT_STATUS_LABELS = {
  [AccountStatus.available]: "可用",
  [AccountStatus.in_use]: "使用中",
  [AccountStatus.done]: "已完成",
  [AccountStatus.failed]: "失败",
} as const

export function accountErrorMessage(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : "操作失败，请检查本地 API 服务"
}
