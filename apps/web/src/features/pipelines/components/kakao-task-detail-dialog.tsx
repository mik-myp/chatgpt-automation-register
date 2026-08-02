import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"

export function KakaoTaskDetailDialog({
  open,
  onOpenChange,
  data,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  data: unknown
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Kakao 任务详情</DialogTitle>
          <DialogDescription>
            本地记录、上游任务与 Kakao 深层状态
          </DialogDescription>
        </DialogHeader>
        <pre className="overflow-auto rounded-sm bg-muted/40 p-3 font-mono text-xs break-all whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      </DialogContent>
    </Dialog>
  )
}
