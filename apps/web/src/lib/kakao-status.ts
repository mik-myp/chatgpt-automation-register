export const KAKAO_PAYMENT_LABELS: Record<string, string> = {
  ready: "等待扫码",
  waiting: "等待扫码",
  opened: "已扫码",
  authenticated: "已验证",
  succeeded: "支付成功",
  completed: "支付成功",
  failed: "支付失败",
  canceled: "已取消",
  expired: "已过期",
}

const TERMINAL_PAYMENT_STATES = new Set([
  "succeeded",
  "completed",
  "failed",
  "canceled",
  "expired",
])

export function paymentStatusLabel(value: string | null | undefined) {
  return KAKAO_PAYMENT_LABELS[value?.toLowerCase() ?? ""] ?? "未知"
}

export function isTerminalPaymentStatus(value: string | null | undefined) {
  return TERMINAL_PAYMENT_STATES.has(value?.toLowerCase() ?? "")
}
