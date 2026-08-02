import {
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  useId,
  useRef,
  useState,
} from "react"
import { FileText, Upload } from "lucide-react"

import { importEntryCount, normalizeImportText } from "@/lib/text-import"
import { Textarea } from "@workspace/ui/components/textarea"
import { cn } from "@workspace/ui/lib/utils"

const MAX_FILE_SIZE = 5 * 1024 * 1024

export function TextFileImportField({
  value,
  onValueChange,
  fileLabel,
  textareaLabel,
  placeholder = "直接粘贴内容",
}: {
  value: string
  onValueChange: (value: string) => void
  fileLabel: string
  textareaLabel: string
  placeholder?: string
}) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState("")
  const [fileError, setFileError] = useState("")
  const count = importEntryCount(value)

  const loadFile = async (file?: File) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith(".txt")) {
      setFileError("请选择 TXT 文件")
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      setFileError("文件不能超过 5 MB")
      return
    }
    try {
      onValueChange(normalizeImportText(await file.text()))
      setFileName(file.name)
      setFileError("")
    } catch {
      setFileError("文件读取失败")
    }
  }

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    void loadFile(event.target.files?.[0])
    event.target.value = ""
  }

  const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setDragging(false)
    void loadFile(event.dataTransfer.files[0])
  }

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = event.clipboardData.getData("text")
    if (!pasted) return
    event.preventDefault()
    setFileName("")
    setFileError("")
    onValueChange(normalizeImportText(pasted))
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return
    event.preventDefault()
    inputRef.current?.click()
  }

  return (
    <div className="grid min-h-0 gap-3">
      <input
        accept=".txt,text/plain"
        aria-label={fileLabel}
        className="sr-only"
        id={inputId}
        onChange={handleFileChange}
        ref={inputRef}
        type="file"
      />
      <button
        aria-describedby={fileError ? `${inputId}-error` : undefined}
        className={cn(
          "flex min-h-20 w-full items-center gap-3 rounded-lg border border-dashed px-4 py-3 text-left transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          dragging
            ? "border-foreground bg-muted"
            : "border-input bg-muted/20 hover:bg-muted/50"
        )}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={(event) => {
          event.preventDefault()
          setDragging(false)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        onKeyDown={handleKeyDown}
        type="button"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-background">
          {value ? <FileText /> : <Upload />}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">
            {value && fileName ? fileName : "选择或拖入 TXT 文件"}
          </span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            {count ? `已识别 ${count} 条` : "点击浏览文件"}
          </span>
        </span>
      </button>
      {fileError && (
        <p className="text-xs text-destructive" id={`${inputId}-error`}>
          {fileError}
        </p>
      )}
      <Textarea
        aria-label={textareaLabel}
        className="field-sizing-fixed h-52 resize-none overflow-y-auto font-mono text-xs leading-5"
        onChange={(event) => {
          setFileName("")
          setFileError("")
          onValueChange(event.target.value)
        }}
        onPaste={handlePaste}
        placeholder={placeholder}
        value={value}
      />
    </div>
  )
}
