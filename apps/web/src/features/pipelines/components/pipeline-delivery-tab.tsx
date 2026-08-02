import { ExternalLink, LinkIcon, Mail, ShieldCheck } from "lucide-react"

import type { PipelineDeliverySummary } from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import {
  PlusStateBadge,
  RowCheckbox,
  SelectionCheckbox,
} from "@/features/pipelines/components/pipeline-ui"
import { TASK_STATUS_LABELS } from "@/features/pipelines/lib/pipeline-state"
import { paymentStatusLabel } from "@/lib/kakao-status"
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

type CopyType = "payment_links" | "account_info"

export function PipelineDeliveryTab({
  rows,
  total,
  itemTotal,
  page,
  selected,
  loading,
  refreshing,
  copyPending,
  checkPending,
  setPage,
  setSelected,
  copy,
  check,
  refresh,
}: {
  rows: PipelineDeliverySummary[]
  total: number
  itemTotal: number
  page: number
  selected: string[]
  loading: boolean
  refreshing: boolean
  copyPending: boolean
  checkPending: boolean
  setPage: (page: number) => void
  setSelected: (ids: string[]) => void
  copy: (copyType: CopyType, taskIds?: string[], all?: boolean) => void
  check: (emails?: string[], allRun?: boolean) => void
  refresh: () => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / 50))
  const selectedEmails = rows
    .filter((item) => selected.includes(item.task_id))
    .map((item) => item.email)
  return (
    <TabsContent
      value="delivery"
      className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden border-t"
    >
      <div className="flex min-h-12 flex-wrap items-center gap-2 border-b py-2">
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {selected.length > 0 && (
            <>
              <Button
                disabled={copyPending}
                onClick={() => copy("payment_links", selected)}
                size="sm"
                variant="outline"
              >
                <LinkIcon />
                已选支付链接 ({selected.length})
              </Button>
              <Button
                disabled={copyPending}
                onClick={() => copy("account_info", selected)}
                size="sm"
                variant="outline"
              >
                <Mail />
                已选邮箱信息 ({selected.length})
              </Button>
              <Button
                disabled={checkPending}
                onClick={() => check(selectedEmails)}
                size="sm"
                variant="outline"
              >
                <ShieldCheck />
                严格检查 Plus
              </Button>
            </>
          )}
          <Button
            disabled={copyPending}
            onClick={() => copy("payment_links", [], true)}
            size="sm"
          >
            <LinkIcon />
            全部支付链接
          </Button>
          <Button
            disabled={copyPending}
            onClick={() => copy("account_info", [], true)}
            size="sm"
          >
            <Mail />
            全部邮箱信息
          </Button>
          <Button
            disabled={checkPending || itemTotal === 0}
            onClick={() => check([], true)}
            size="sm"
            variant="outline"
          >
            <ShieldCheck />
            严格检查全部 Plus
          </Button>
          <TableRefreshButton
            isRefreshing={refreshing}
            label="刷新交付信息"
            onRefresh={refresh}
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <Table className="min-w-280">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <SelectionCheckbox
                  ids={rows
                    .filter(
                      (item) => item.payment_copyable || item.account_copyable
                    )
                    .map((item) => item.task_id)}
                  selected={selected}
                  setSelected={setSelected}
                />
              </TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>支付链接</TableHead>
              <TableHead>提取状态</TableHead>
              <TableHead>扫码状态</TableHead>
              <TableHead>密码</TableHead>
              <TableHead>MFA</TableHead>
              <TableHead>Plus</TableHead>
              <TableHead>邮箱复制格式</TableHead>
              <TableHead className="w-24 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={item.task_id}>
                <TableCell>
                  {item.deliverable ? (
                    <RowCheckbox
                      id={item.task_id}
                      selected={selected}
                      setSelected={setSelected}
                    />
                  ) : (
                    "-"
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {item.email}
                </TableCell>
                <TableCell className="max-w-80">
                  {item.payment_url ? (
                    <a
                      className="block truncate font-mono text-xs text-sky-700 hover:underline dark:text-sky-300"
                      href={item.payment_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {item.payment_url}
                    </a>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      尚未生成
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={item.task_status}
                    label={TASK_STATUS_LABELS[item.task_status]}
                  />
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={item.payment_status}
                    label={paymentStatusLabel(item.payment_status)}
                  />
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={item.password_status}
                    label={item.password_status === "set" ? "已设置" : "未完成"}
                  />
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={item.mfa_status}
                    label={item.mfa_status === "enabled" ? "已启用" : "未完成"}
                  />
                </TableCell>
                <TableCell>
                  <PlusStateBadge
                    state={item.plus_state}
                    label={item.plus_label}
                    error={item.plus_error}
                  />
                </TableCell>
                <TableCell>
                  <StatusBadge
                    status={item.account_format}
                    label={
                      item.account_format === "security_credentials"
                        ? "安全凭证"
                        : item.account_format === "mail_access"
                          ? "邮箱访问"
                          : "不可复制"
                    }
                  />
                  {item.account_missing_reason && (
                    <span className="ml-2 text-xs text-destructive">
                      {item.account_missing_reason}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    aria-label={`复制 ${item.email} 的支付链接`}
                    disabled={!item.payment_copyable || copyPending}
                    onClick={() => copy("payment_links", [item.task_id])}
                    size="icon-sm"
                    title="复制支付链接"
                    variant="ghost"
                  >
                    <LinkIcon />
                  </Button>
                  <Button
                    aria-label={`复制 ${item.email} 的邮箱信息`}
                    disabled={!item.account_copyable || copyPending}
                    onClick={() => copy("account_info", [item.task_id])}
                    size="icon-sm"
                    title={item.account_missing_reason ?? "复制邮箱信息"}
                    variant="ghost"
                  >
                    <Mail />
                  </Button>
                  {item.payment_url && (
                    <Button
                      asChild
                      size="icon-sm"
                      title="打开支付链接"
                      variant="ghost"
                    >
                      <a
                        href={item.payment_url}
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
                  colSpan={10}
                >
                  本轮次暂无交付信息
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
