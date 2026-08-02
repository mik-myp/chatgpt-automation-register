import { useState } from "react"
import { Link, useSearchParams } from "react-router"
import { useQueryClient } from "@tanstack/react-query"
import { Ban, ChevronRight, Inbox, Pause, Play, Trash2, X } from "lucide-react"
import { toast } from "sonner"

import {
  BulkPipelineAction,
  getListPipelineRunsApiPipelinesRunsGetQueryKey,
  PipelineRunKind,
  PipelineStatus,
  type PipelineStatus as PipelineStatusType,
  useBulkPipelineActionApiPipelinesRunsBatchPost,
  useListPipelineRunsApiPipelinesRunsGet,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import { CreateRegistrationDialog } from "@/features/pipelines/components/create-registration-dialog"
import { CreateKakaoPipelineDialog } from "@/features/pipelines/components/create-kakao-dialog"
import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import {
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import {
  pipelineStatus,
  PIPELINE_KIND_LABELS,
  RUN_STATUS_LABELS,
} from "@/features/pipelines/lib/pipeline-state"
import {
  PIPELINE_PAGE_SIZE,
  pipelineListState,
} from "@/features/pipelines/lib/pipeline-route-state"
import { ApiError } from "@/lib/api-client"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

export function PipelinesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string[]>([])
  const [deleteIds, setDeleteIds] = useState<string[]>([])
  const { status, page, params } = pipelineListState(searchParams)
  const query = useListPipelineRunsApiPipelinesRunsGet(params, {
    query: {
      queryKey: getListPipelineRunsApiPipelinesRunsGetQueryKey(params),
      refetchInterval: (current) => {
        if (document.visibilityState === "hidden") return false
        return current.state.data?.items.some(
          (run) =>
            run.status === PipelineStatus.queued ||
            run.status === PipelineStatus.running ||
            run.status === PipelineStatus.paused
        )
          ? 2000
          : false
      },
    },
  })
  const mutation = useBulkPipelineActionApiPipelinesRunsBatchPost<ApiError>({
    mutation: {
      onSuccess: (result, variables) => {
        void queryClient.invalidateQueries({
          queryKey: ["/api/pipelines/runs"],
        })
        setSelected([])
        const skipped = result.skipped ? `，跳过 ${result.skipped}` : ""
        const labels = {
          [BulkPipelineAction.cancel]: "取消",
          [BulkPipelineAction.pause]: "暂停",
          [BulkPipelineAction.resume]: "恢复",
          [BulkPipelineAction.delete]: "删除",
        }
        if (variables.data.action === BulkPipelineAction.delete) {
          setDeleteIds([])
        }
        toast.success(
          `${labels[variables.data.action]}完成：处理 ${result.processed}${skipped}`
        )
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const rows = query.data?.items ?? []
  const selectedRows = rows.filter((run) => selected.includes(run.id))
  const pauseIds = selectedRows
    .filter(
      (run) =>
        run.kind === PipelineRunKind.registration &&
        (
          [
            PipelineStatus.queued,
            PipelineStatus.running,
          ] as PipelineStatusType[]
        ).includes(run.status)
    )
    .map((run) => run.id)
  const resumeIds = selectedRows
    .filter(
      (run) =>
        run.kind === PipelineRunKind.registration &&
        run.status === PipelineStatus.paused
    )
    .map((run) => run.id)
  const cancelIds = selectedRows
    .filter((run) =>
      (
        [
          PipelineStatus.queued,
          PipelineStatus.running,
          PipelineStatus.paused,
        ] as PipelineStatusType[]
      ).includes(run.status)
    )
    .map((run) => run.id)
  const removableIds = selectedRows
    .filter((run) =>
      (
        [
          PipelineStatus.completed,
          PipelineStatus.failed,
          PipelineStatus.canceled,
        ] as PipelineStatusType[]
      ).includes(run.status)
    )
    .map((run) => run.id)
  const total = query.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PIPELINE_PAGE_SIZE))

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">流水线轮次</h1>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <CreateKakaoPipelineDialog />
          <CreateSecurityPipelineDialog />
          <CreateRegistrationDialog
            defaultEmail={searchParams.get("email") ?? ""}
          />
        </div>
      </div>

      <section
        className="flex min-h-0 min-w-0 flex-1 flex-col border-t"
        aria-label="流水线轮次列表"
      >
        <div className="flex flex-wrap items-center gap-2 border-b py-3">
          <Select
            value={status}
            onValueChange={(value) => {
              setSearchParams((current) => {
                const next = new URLSearchParams(current)
                if (value === "all") next.delete("status")
                else next.set("status", value)
                next.delete("page")
                return next
              })
              setSelected([])
            }}
          >
            <SelectTrigger aria-label="轮次状态" className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              {Object.entries(RUN_STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
            {selected.length > 0 && (
              <>
                <span className="text-xs font-medium">
                  已选 {selected.length} 项
                </span>
                {pauseIds.length > 0 && (
                  <Button
                    disabled={mutation.isPending}
                    onClick={() =>
                      mutation.mutate({
                        data: {
                          action: BulkPipelineAction.pause,
                          run_ids: pauseIds,
                        },
                      })
                    }
                    size="sm"
                    variant="outline"
                  >
                    <Pause />
                    暂停
                  </Button>
                )}
                {resumeIds.length > 0 && (
                  <Button
                    disabled={mutation.isPending}
                    onClick={() =>
                      mutation.mutate({
                        data: {
                          action: BulkPipelineAction.resume,
                          run_ids: resumeIds,
                        },
                      })
                    }
                    size="sm"
                    variant="outline"
                  >
                    <Play />
                    恢复
                  </Button>
                )}
                {cancelIds.length > 0 && (
                  <Button
                    disabled={mutation.isPending}
                    onClick={() =>
                      mutation.mutate({
                        data: {
                          action: BulkPipelineAction.cancel,
                          run_ids: cancelIds,
                        },
                      })
                    }
                    size="sm"
                    variant="outline"
                  >
                    <Ban />
                    取消轮次
                  </Button>
                )}
                {removableIds.length > 0 && (
                  <Button
                    disabled={mutation.isPending}
                    onClick={() => setDeleteIds(removableIds)}
                    size="sm"
                    variant="destructive"
                  >
                    <Trash2 />
                    删除
                  </Button>
                )}
                <Button
                  aria-label="清除选择"
                  onClick={() => setSelected([])}
                  size="icon-sm"
                  variant="ghost"
                >
                  <X />
                </Button>
              </>
            )}
            <TableRefreshButton
              isRefreshing={query.isFetching}
              label="刷新流水线轮次"
              onRefresh={() => void query.refetch()}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Table className="min-w-190">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <SelectionCheckbox
                    ids={rows.map((row) => row.id)}
                    selected={selected}
                    setSelected={setSelected}
                  />
                </TableHead>
                <TableHead>轮次</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>目标</TableHead>
                <TableHead>完成</TableHead>
                <TableHead>Kakao 任务</TableHead>
                <TableHead>开始时间</TableHead>
                <TableHead className="w-32 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>
                    <RowCheckbox
                      id={run.id}
                      selected={selected}
                      setSelected={setSelected}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <Link
                      className="hover:underline"
                      to={`/pipelines/${run.id}`}
                    >
                      {run.id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={run.kind}
                      label={PIPELINE_KIND_LABELS[run.kind]}
                    />
                  </TableCell>
                  <TableCell>
                    <StatusBadge {...pipelineStatus(run)} />
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {run.target_count}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {run.registered_count}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {run.kakao_task_count}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatCompactBeijingDateTime(
                      run.started_at ?? run.created_at
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {run.kind === PipelineRunKind.registration &&
                      run.registered_count > 0 && (
                        <>
                          {!run.kakao_enabled && (
                            <CreateKakaoPipelineDialog
                              iconOnly
                              sourceRunId={run.id}
                            />
                          )}
                          <CreateSecurityPipelineDialog
                            iconOnly
                            sourceRunId={run.id}
                          />
                        </>
                      )}
                    {run.kind === PipelineRunKind.registration &&
                      (run.status === PipelineStatus.queued ||
                        run.status === PipelineStatus.running) && (
                        <Button
                          aria-label={`暂停轮次 ${run.id}`}
                          disabled={mutation.isPending}
                          onClick={() =>
                            mutation.mutate({
                              data: {
                                action: BulkPipelineAction.pause,
                                run_ids: [run.id],
                              },
                            })
                          }
                          size="icon-sm"
                          title="暂停"
                          variant="ghost"
                        >
                          <Pause />
                        </Button>
                      )}
                    {run.kind === PipelineRunKind.registration &&
                      run.status === PipelineStatus.paused && (
                        <Button
                          aria-label={`恢复轮次 ${run.id}`}
                          disabled={mutation.isPending}
                          onClick={() =>
                            mutation.mutate({
                              data: {
                                action: BulkPipelineAction.resume,
                                run_ids: [run.id],
                              },
                            })
                          }
                          size="icon-sm"
                          title="恢复"
                          variant="ghost"
                        >
                          <Play />
                        </Button>
                      )}
                    {(run.status === PipelineStatus.queued ||
                      run.status === PipelineStatus.running ||
                      run.status === PipelineStatus.paused) && (
                      <Button
                        aria-label={`取消轮次 ${run.id}`}
                        disabled={mutation.isPending}
                        onClick={() =>
                          mutation.mutate({
                            data: {
                              action: BulkPipelineAction.cancel,
                              run_ids: [run.id],
                            },
                          })
                        }
                        size="icon-sm"
                        title="取消"
                        variant="ghost"
                      >
                        <Ban />
                      </Button>
                    )}
                    {(run.status === PipelineStatus.completed ||
                      run.status === PipelineStatus.failed ||
                      run.status === PipelineStatus.canceled) && (
                      <Button
                        aria-label={`删除轮次 ${run.id}`}
                        disabled={mutation.isPending}
                        onClick={() => setDeleteIds([run.id])}
                        size="icon-sm"
                        title="删除"
                        variant="ghost"
                      >
                        <Trash2 />
                      </Button>
                    )}
                    <Button
                      asChild
                      aria-label={`查看轮次 ${run.id}`}
                      size="icon-sm"
                      variant="ghost"
                    >
                      <Link to={`/pipelines/${run.id}`}>
                        <ChevronRight />
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!query.isLoading && !rows.length && (
                <TableRow>
                  <TableCell className="h-52 text-center" colSpan={9}>
                    <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                    <p className="text-sm font-medium">暂无流水线轮次</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <TablePagination
          page={page}
          pageCount={pageCount}
          total={total}
          onPageChange={(value) => {
            setSearchParams((current) => {
              const next = new URLSearchParams(current)
              if (value === 0) next.delete("page")
              else next.set("page", String(value + 1))
              return next
            })
            setSelected([])
          }}
        />
      </section>
      <AlertDialog
        open={deleteIds.length > 0}
        onOpenChange={(open) => !open && setDeleteIds([])}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              删除 {deleteIds.length} 个流水线轮次？
            </AlertDialogTitle>
            <AlertDialogDescription>
              仅已完成、失败或已取消的轮次可以删除。注册结果和 Kakao
              任务会保留，轮次详情及卡密分配记录将被移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={mutation.isPending}
              onClick={() =>
                mutation.mutate({
                  data: {
                    action: BulkPipelineAction.delete,
                    run_ids: deleteIds,
                  },
                })
              }
              variant="destructive"
            >
              {mutation.isPending ? "正在删除" : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
