import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { toast } from "sonner"

import { useImportCardsApiKakaoCardsImportPost } from "@/api/generated"
import { TextFileImportField } from "@/components/text-file-import-field"
import { refreshCardQueries } from "@/features/cards/lib/card-queries"
import { ApiError } from "@/lib/api-client"
import { importEntryCount, normalizeImportText } from "@/lib/text-import"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"

export function ImportCardsDialog({
  open,
  setOpen,
}: {
  open: boolean
  setOpen: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [text, setText] = useState("")
  const entryCount = importEntryCount(text)
  const mutation = useImportCardsApiKakaoCardsImportPost<ApiError>({
    mutation: {
      onSuccess: (result) => {
        void refreshCardQueries(queryClient)
        setOpen(false)
        setText("")
        const duplicates = result.duplicates
          ? `，跳过重复 ${result.duplicates}`
          : ""
        toast.success(`导入完成：新增 ${result.inserted}${duplicates}`)
      },
      onError: (error) => toast.error(error.message),
    },
  })
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>导入卡密</DialogTitle>
          <DialogDescription>
            选择文件或直接粘贴，重复卡密自动跳过。
          </DialogDescription>
        </DialogHeader>
        <TextFileImportField
          fileLabel="选择卡密导入文件"
          onValueChange={setText}
          placeholder="直接粘贴卡密内容"
          textareaLabel="卡密内容"
          value={text}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={!entryCount || mutation.isPending}
            onClick={() =>
              mutation.mutate({ data: { text: normalizeImportText(text) } })
            }
          >
            <Upload />
            {mutation.isPending ? "正在导入" : `导入卡密（${entryCount}）`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
