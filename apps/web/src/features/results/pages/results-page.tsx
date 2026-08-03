import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Download, Send, ShieldCheck, Trash2 } from "lucide-react"
import { toast } from "sonner"

import {
  type ResultOperationSummary,
  useDeleteResultsApiResultsBatchDeletePost,
  useExportResultsApiResultsExportPost,
} from "@/api/generated"
import { ResultOperationList } from "@/features/results/components/result-operation-list"
import { ResultsTable } from "@/features/results/components/results-table"
import { downloadResultsJson } from "@/features/results/lib/result-actions"
import { runResultOperation } from "@/features/results/lib/result-operations"
import { ApiError } from "@/lib/api-client"
import { TOUR_IDS } from "@/lib/product-tours"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@workspace/ui/components/alert-dialog"
import { Button } from "@workspace/ui/components/button"

export function ResultsPage() {
  const queryClient = useQueryClient()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const exportMutation = useExportResultsApiResultsExportPost<ApiError>({
    mutation: {
      onSuccess: (data) => {
        downloadResultsJson(data.items)
        toast.success(`已导出 ${data.items.length} 条注册结果`)
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const deleteMutation = useDeleteResultsApiResultsBatchDeletePost<ApiError>({
    mutation: {
      onSuccess: (data) => {
        void queryClient.invalidateQueries({ queryKey: ["/api/results"] })
        setDeleteOpen(false)
        toast.success(`已删除 ${data.processed} 条注册结果`)
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const plusMutation = useMutation<ResultOperationSummary, ApiError, void>({
    mutationFn: () =>
      runResultOperation("/api/results/check-plus", { emails: [], all: true }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["/api/results"] })
      toast.success(
        `Plus 检查完成：确认 Plus ${data.plus}/${data.total}${data.unknown ? `，无法确认 ${data.unknown}` : ""}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const publishMutation = useMutation<
    ResultOperationSummary,
    ApiError,
    "cpa" | "sub2api"
  >({
    mutationFn: (target) =>
      runResultOperation("/api/results/publish", {
        emails: [],
        all: true,
        targets: [target],
      }),
    onSuccess: (data, target) => {
      if (data.failed)
        toast.error(`${target.toUpperCase()} 发布失败 ${data.failed} 条`)
      else toast.success(`${target.toUpperCase()} 已发布 ${data.succeeded} 条`)
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div
        className="flex flex-wrap items-center justify-between gap-2"
        id={TOUR_IDS.resultsHeader}
      >
        <h1 className="text-xl font-semibold">注册结果</h1>
        <div
          className="flex flex-wrap items-center justify-end gap-1.5"
          id={TOUR_IDS.resultsActions}
        >
          <Button
            disabled={plusMutation.isPending}
            onClick={() => plusMutation.mutate()}
            size="sm"
            variant="outline"
          >
            <ShieldCheck />
            严格检查全部 Plus
          </Button>
          <Button
            disabled={publishMutation.isPending}
            onClick={() => publishMutation.mutate("cpa")}
            size="sm"
            variant="outline"
          >
            <Send />
            全部到 CPA
          </Button>
          <Button
            disabled={publishMutation.isPending}
            onClick={() => publishMutation.mutate("sub2api")}
            size="sm"
            variant="outline"
          >
            <Send />
            全部到 SUB2API
          </Button>
          <Button
            onClick={() =>
              exportMutation.mutate({ data: { all: true, emails: [] } })
            }
            size="sm"
            variant="outline"
          >
            <Download />
            导出全部
          </Button>
          <Button
            onClick={() => setDeleteOpen(true)}
            size="sm"
            variant="destructive"
          >
            <Trash2 />
            删除全部
          </Button>
        </div>
      </div>
      <ResultOperationList />
      <div className="flex min-h-0 flex-1">
        <ResultsTable />
      </div>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除全部注册结果？</AlertDialogTitle>
            <AlertDialogDescription>
              凭证和令牌将永久删除，号池账号不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                deleteMutation.mutate({ data: { emails: [], all: true } })
              }
              variant="destructive"
            >
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
