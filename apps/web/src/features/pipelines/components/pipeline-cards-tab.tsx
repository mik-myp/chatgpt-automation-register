import { Fragment } from "react"
import { ChevronRight } from "lucide-react"

import type { PipelineCardAllocationSummary } from "@/api/generated"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"
import { TabsContent } from "@workspace/ui/components/tabs"

export function PipelineCardsTab({
  rows,
  total,
  page,
  selected,
  refreshing,
  setPage,
  setSelected,
  refresh,
}: {
  rows: PipelineCardAllocationSummary[]
  total: number
  page: number
  selected: string[]
  refreshing: boolean
  setPage: (page: number) => void
  setSelected: (ids: string[]) => void
  refresh: () => void
}) {
  const selectedCards = rows.filter((card) => selected.includes(card.card_id))
  const pageCount = Math.max(1, Math.ceil(total / 50))
  return (
    <TabsContent
      value="cards"
      className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
    >
      <div className="flex min-h-12 items-center border-b py-2">
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <CopySelectionBar
            selected={selected}
            values={selectedCards.map((card) => card.card_code)}
            label="卡密"
            clear={() => setSelected([])}
          />
          <TableRefreshButton
            isRefreshing={refreshing}
            label="刷新卡密分配"
            onRefresh={refresh}
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <SelectionCheckbox
                  ids={rows.map((card) => card.card_id)}
                  selected={selected}
                  setSelected={setSelected}
                />
              </TableHead>
              <TableHead>卡密</TableHead>
              <TableHead>分配统计</TableHead>
              <TableHead>使用邮箱</TableHead>
              <TableHead>任务 ID</TableHead>
              <TableHead>任务状态</TableHead>
              <TableHead>支付状态</TableHead>
              <TableHead>扣卡</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((card) => {
              const assignments = card.assignments ?? []
              return (
                <Fragment key={card.card_id}>
                  <TableRow className="bg-muted/20">
                    <TableCell>
                      <RowCheckbox
                        id={card.card_id}
                        selected={selected}
                        setSelected={setSelected}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium">
                      {card.card_code}
                    </TableCell>
                    <TableCell className="text-xs tabular-nums">
                      分配 {card.allocated_count} · 创建 {card.created_count} ·
                      重复 {card.duplicate_count} · 失败 {card.failed_count}
                    </TableCell>
                    <TableCell
                      colSpan={5}
                      className="text-xs text-muted-foreground"
                    >
                      {assignments.length
                        ? `${assignments.length} 个邮箱任务`
                        : "尚未生成 Kakao 任务"}
                    </TableCell>
                  </TableRow>
                  {assignments.map((assignment) => (
                    <TableRow key={assignment.task_id}>
                      <TableCell />
                      <TableCell className="pl-6 text-xs text-muted-foreground">
                        <ChevronRight className="size-3" />
                      </TableCell>
                      <TableCell />
                      <TableCell className="font-mono text-xs">
                        {assignment.email}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {assignment.task_id}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          status={assignment.status}
                          label={TASK_STATUS_LABELS[assignment.status]}
                        />
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          status={assignment.payment_status}
                          label={paymentStatusLabel(assignment.payment_status)}
                        />
                      </TableCell>
                      <TableCell>
                        {assignment.card_charged == null
                          ? "-"
                          : assignment.card_charged
                            ? "是"
                            : "否"}
                      </TableCell>
                    </TableRow>
                  ))}
                </Fragment>
              )
            })}
            {!rows.length && (
              <TableRow>
                <TableCell
                  className="h-40 text-center text-sm text-muted-foreground"
                  colSpan={8}
                >
                  本轮次未分配卡密
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
