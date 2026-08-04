import { Ban, ExternalLink, Eye, Play, RefreshCw } from "lucide-react"

import { KakaoTaskStatus, type KakaoTaskSummary } from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import {
  CopySelectionBar,
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import { TASK_STATUS_LABELS } from "@/features/pipelines/lib/pipeline-state"
import { paymentStatusLabel } from "@/lib/kakao-status"
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
import { TabsContent } from "@workspace/ui/components/tabs"

type TaskAction = "sync" | "cancel" | "retry"

export function KakaoTasksTab({
  rows,
  total,
  page,
  status,
  selected,
  pending,
  loading,
  refreshing,
  setPage,
  setStatus,
  setSelected,
  action,
  detail,
  refresh,
}: {
  rows: KakaoTaskSummary[]
  total: number
  page: number
  status: KakaoTaskStatus | "all"
  selected: string[]
  pending: boolean
  loading: boolean
  refreshing: boolean
  setPage: (page: number) => void
  setStatus: (status: KakaoTaskStatus | "all") => void
  setSelected: (ids: string[]) => void
  action: (action: TaskAction, ids?: string[]) => void
  detail: (id: string) => void
  refresh: () => void
}) {
  const selectedTasks = rows.filter((task) => selected.includes(task.id))
  const pageCount = Math.max(1, Math.ceil(total / 50))
  return (
    <TabsContent
      value="kakao"
      className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
    >
      <div className="flex min-h-12 items-center border-b py-2">
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value as KakaoTaskStatus | "all")
            setPage(0)
            setSelected([])
          }}
        >
          <SelectTrigger
            aria-label="Kakao 任务状态"
            className="mr-2 w-32"
            size="sm"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            {Object.values(KakaoTaskStatus).map((value) => (
              <SelectItem key={value} value={value}>
                {TASK_STATUS_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <CopySelectionBar
            selected={selected}
            values={selectedTasks.map((task) => task.upstream_job_id)}
            label="任务 ID"
            clear={() => setSelected([])}
          />
          {selected.length > 0 && (
            <div className="flex items-center gap-1.5">
              <Button
                disabled={pending}
                onClick={() => action("sync")}
                size="sm"
                variant="outline"
              >
                <RefreshCw />
                同步
              </Button>
              <Button
                disabled={pending}
                onClick={() => action("retry")}
                size="sm"
                variant="outline"
              >
                <Play />
                重试
              </Button>
              <Button
                disabled={pending}
                onClick={() => action("cancel")}
                size="sm"
                variant="outline"
              >
                <Ban />
                取消
              </Button>
            </div>
          )}
          <TableRefreshButton
            isRefreshing={refreshing}
            label="刷新 Kakao 任务"
            onRefresh={refresh}
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Table className="min-w-190">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <SelectionCheckbox
                  ids={rows.map((task) => task.id)}
                  selected={selected}
                  setSelected={setSelected}
                />
              </TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>任务 ID</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>支付状态</TableHead>
              <TableHead>扣卡</TableHead>
              <TableHead className="w-32 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((task) => (
              <TableRow key={task.id}>
                <TableCell>
                  <RowCheckbox
                    id={task.id}
                    selected={selected}
                    setSelected={setSelected}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {task.email}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {task.upstream_job_id}
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={task.status}
                    label={TASK_STATUS_LABELS[task.status]}
                  />
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={task.payment_status}
                    label={paymentStatusLabel(task.payment_status)}
                  />
                </TableCell>
                <TableCell>
                  {task.card_charged == null
                    ? "-"
                    : task.card_charged
                      ? "是"
                      : "否"}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    aria-label="查看任务详情"
                    onClick={() => detail(task.id)}
                    size="icon-sm"
                    title="查看详情"
                    variant="ghost"
                  >
                    <Eye />
                  </Button>
                  <Button
                    aria-label="重试任务"
                    disabled={pending}
                    onClick={() => action("retry", [task.id])}
                    size="icon-sm"
                    title="重试"
                    variant="ghost"
                  >
                    <Play />
                  </Button>
                  <Button
                    aria-label="取消任务"
                    disabled={pending}
                    onClick={() => action("cancel", [task.id])}
                    size="icon-sm"
                    title="取消"
                    variant="ghost"
                  >
                    <Ban />
                  </Button>
                  {task.payment_url && (
                    <Button
                      asChild
                      aria-label="打开支付链接"
                      size="icon-sm"
                      variant="ghost"
                    >
                      <a
                        href={task.payment_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <ExternalLink />
                      </a>
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!loading && !rows.length && (
              <TableRow>
                <TableCell
                  className="h-40 text-center text-sm text-muted-foreground"
                  colSpan={7}
                >
                  本轮次暂无 Kakao 任务
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
          setPage(value)
          setSelected([])
        }}
      />
    </TabsContent>
  )
}
