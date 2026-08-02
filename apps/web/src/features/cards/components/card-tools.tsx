import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { toast } from "sonner"

import { useImportCardsApiKakaoCardsImportPost } from "@/api/generated"
import { refreshCardQueries } from "@/features/cards/lib/card-queries"
import { ApiError } from "@/lib/api-client"
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
import { Textarea } from "@workspace/ui/components/textarea"

export function ImportCardsDialog({
  open,
  setOpen,
}: {
  open: boolean
  setOpen: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [text, setText] = useState("")
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
          <DialogDescription>重复卡密会自动跳过。</DialogDescription>
        </DialogHeader>
        <Textarea
          aria-label="卡密列表"
          className="min-h-72 resize-y font-mono text-xs"
          onChange={(event) => setText(event.target.value)}
          placeholder="KA-XXXX-XXXX"
          value={text}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={!text.trim() || mutation.isPending}
            onClick={() => mutation.mutate({ data: { text } })}
          >
            <Upload />
            {mutation.isPending ? "正在导入" : "导入卡密"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
