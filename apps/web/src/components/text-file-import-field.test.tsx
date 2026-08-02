import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { TextFileImportField } from "@/components/text-file-import-field"

afterEach(cleanup)

function textFile(name: string, text: string) {
  const file = new File([text], name, { type: "text/plain" })
  Object.defineProperty(file, "text", {
    value: vi.fn().mockResolvedValue(text),
  })
  return file
}

describe("TextFileImportField", () => {
  it("loads and normalizes a selected file", async () => {
    const user = userEvent.setup()
    const onValueChange = vi.fn()
    render(
      <TextFileImportField
        fileLabel="选择邮箱导入文件"
        onValueChange={onValueChange}
        textareaLabel="邮箱内容"
        value=""
      />
    )
    const file = textFile(
      "邮箱一键复制.txt",
      "=== 使用说明 ===\n说明\n=== 卡密内容 ===\nmail@example.com---https://mail.example.com"
    )

    await user.upload(screen.getByLabelText("选择邮箱导入文件"), file)

    await waitFor(() =>
      expect(onValueChange).toHaveBeenCalledWith(
        "mail@example.com---https://mail.example.com"
      )
    )
  })

  it("loads a dropped file", async () => {
    const onValueChange = vi.fn()
    render(
      <TextFileImportField
        fileLabel="选择卡密导入文件"
        onValueChange={onValueChange}
        textareaLabel="卡密内容"
        value=""
      />
    )
    const file = textFile("卡密导出.txt", "卡密导出\n\nFIRST-CARD")

    fireEvent.drop(screen.getByRole("button"), {
      dataTransfer: { files: [file] },
    })

    await waitFor(() =>
      expect(onValueChange).toHaveBeenCalledWith("FIRST-CARD")
    )
  })

  it("cleans wrapped text when pasted", () => {
    const onValueChange = vi.fn()
    render(
      <TextFileImportField
        fileLabel="选择卡密导入文件"
        onValueChange={onValueChange}
        textareaLabel="卡密内容"
        value=""
      />
    )

    fireEvent.paste(screen.getByLabelText("卡密内容"), {
      clipboardData: {
        getData: () =>
          "=== 使用说明 ===\n说明\n=== 卡密内容 ===\nFIRST-CARD\nSECOND-CARD",
      },
    })

    expect(onValueChange).toHaveBeenCalledWith("FIRST-CARD\nSECOND-CARD")
  })
})
