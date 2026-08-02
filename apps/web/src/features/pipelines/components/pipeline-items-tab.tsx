import { RefreshCw } from "lucide-react"

import type { PipelineItemSummary } from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import {
  CopySelectionBar,
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import { TASK_STATUS_LABELS } from "@/features/pipelines/lib/pipeline-state"
import { Button } from "@workspace/ui/components/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"
import { TabsContent } from "@workspace/ui/components/tabs"

export function PipelineItemsTab({
  isKakao,
  rows,
  total,
  page,
  selected,
  retrying,
  refreshing,
  setPage,
  setSelected,
  retry,
  refresh,
}: {
  isKakao: boolean
  rows: PipelineItemSummary[]
  total: number
  page: number
  selected: string[]
  retrying: boolean
  refreshing: boolean
  setPage: (page: number) => void
  setSelected: (ids: string[]) => void
  retry: (ids: string[]) => void
  refresh: () => void
}) {
  const selectedItems = rows.filter((item) => selected.includes(item.id))
  const pageCount = Math.max(1, Math.ceil(total / 50))
  return (
    <TabsContent
      value="items"
      className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
    >
      <div className="flex min-h-12 items-center border-b py-2">
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <CopySelectionBar
            selected={selected}
            values={selectedItems
              .map((item) => item.account_email)
              .filter((value): value is string => Boolean(value))}
            label="邮箱"
            clear={() => setSelected([])}
          />
          {selected.length > 0 && (
            <Button
              disabled={retrying}
              onClick={() => retry(selected)}
              size="sm"
              variant="outline"
            >
              <RefreshCw />
              重跑失败项
            </Button>
          )}
          <TableRefreshButton
            isRefreshing={refreshing}
            label={isKakao ? "刷新 Kakao 账号" : "刷新注册项"}
            onRefresh={refresh}
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Table className="min-w-220">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <SelectionCheckbox
                  ids={rows.map((item) => item.id)}
                  selected={selected}
                  setSelected={setSelected}
                />
              </TableHead>
              <TableHead>序号</TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>资格</TableHead>
              <TableHead>错误</TableHead>
              <TableHead className="w-14 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  <RowCheckbox
                    id={item.id}
                    selected={selected}
                    setSelected={setSelected}
                  />
                </TableCell>
                <TableCell className="tabular-nums">
                  {item.position + 1}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {item.account_email ?? "-"}
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={item.status}
                    label={TASK_STATUS_LABELS[item.status]}
                  />
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {item.eligibility_state ?? "-"}
                </TableCell>
                <TableCell className="max-w-72 truncate text-xs text-red-600">
                  {item.error ?? "-"}
                </TableCell>
                <TableCell className="text-right">
                  {(item.status === "failed" || item.status === "skipped") && (
                    <Button
                      aria-label={`重跑第 ${item.position + 1} 项`}
                      disabled={retrying}
                      onClick={() => retry([item.id])}
                      size="icon-sm"
                      title="重跑"
                      variant="ghost"
                    >
                      <RefreshCw />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!rows.length && (
              <TableRow>
                <TableCell
                  className="h-40 text-center text-sm text-muted-foreground"
                  colSpan={7}
                >
                  {isKakao ? "本轮次暂无 Kakao 账号" : "本轮次暂无注册项"}
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
