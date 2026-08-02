import { describe, expect, it } from "vitest"

import { isTerminalPaymentStatus, paymentStatusLabel } from "./kakao-status"

describe("Kakao payment protocol states", () => {
  it.each([
    ["READY", "等待扫码", false],
    ["OPENED", "已扫码", false],
    ["AUTHENTICATED", "已验证", false],
    ["COMPLETED", "支付成功", true],
    ["CANCELED", "已取消", true],
    ["FAILED", "支付失败", true],
    ["EXPIRED", "已过期", true],
  ])("maps %s consistently", (state, label, terminal) => {
    expect(paymentStatusLabel(state)).toBe(label)
    expect(isTerminalPaymentStatus(state)).toBe(terminal)
  })
})
