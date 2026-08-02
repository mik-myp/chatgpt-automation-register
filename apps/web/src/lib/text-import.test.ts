import { describe, expect, it } from "vitest"

import { importEntryCount, normalizeImportText } from "@/lib/text-import"

describe("normalizeImportText", () => {
  it("extracts entries from one-click copy text", () => {
    const text =
      "\ufeff=== 使用说明 ===\n不要导入这段说明\n\n=== 卡密内容 ===\nFIRST\nSECOND\n"

    expect(normalizeImportText(text)).toBe("FIRST\nSECOND")
    expect(importEntryCount(text)).toBe(2)
  })

  it("removes export headings", () => {
    expect(normalizeImportText("\ufeff卡密导出\r\n\r\nFIRST\r\n")).toBe("FIRST")
  })
})
