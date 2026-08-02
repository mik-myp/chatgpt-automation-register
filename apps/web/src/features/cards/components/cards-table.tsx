import { Inbox, Power, PowerOff, Trash2 } from "lucide-react"

import {
  BulkCardAction,
  type CardInventoryItem,
  type CardUsageItem,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { formatBeijingDateTime } from "@/lib/date-time"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

export function CardsTable({
  rows,
  usageByCard,
  selected,
  setSelected,
  loading,
  error,
  pending,
  onToggle,
  onDelete,
}: {
  rows: CardInventoryItem[]
  usageByCard: Map<string, CardUsageItem>
  selected: string[]
  setSelected: (ids: string[]) => void
  loading: boolean
  error: boolean
  pending: boolean
  onToggle: (action: BulkCardAction, cardId: string) => void
  onDelete: (cardId: string) => void
}) {
  const ids = rows.map((card) => card.id)
  const selectedCount = ids.filter((id) => selected.includes(id)).length

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <Table className="min-w-200">
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                aria-label="选择当前表格全部卡密"
                checked={
                  ids.length > 0 && selectedCount === ids.length
                    ? true
                    : selectedCount > 0
                      ? "indeterminate"
                      : false
                }
                onCheckedChange={(checked) => setSelected(checked ? ids : [])}
              />
            </TableHead>
            <TableHead>卡密</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>使用轮次</TableHead>
            <TableHead>分配</TableHead>
            <TableHead>创建</TableHead>
            <TableHead>失败</TableHead>
            <TableHead>实时已扣</TableHead>
            <TableHead>实时占用</TableHead>
            <TableHead>实时剩余</TableHead>
            <TableHead>最后检查</TableHead>
            <TableHead className="w-32 text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((card) => {
            const usage = usageByCard.get(card.id) ?? {
              error: card.usage_error,
              charged: card.cached_charged,
              pending: card.cached_pending,
              remaining: card.cached_remaining,
            }
            return (
              <TableRow key={card.id}>
                <TableCell>
                  <Checkbox
                    aria-label={`选择 ${card.code}`}
                    checked={selected.includes(card.id)}
                    onCheckedChange={() =>
                      setSelected(
                        selected.includes(card.id)
                          ? selected.filter((id) => id !== card.id)
                          : [...selected, card.id]
                      )
                    }
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">{card.code}</TableCell>
                <TableCell>
                  <StatusBadge
                    status={card.active ? "enabled" : "canceled"}
                    label={card.active ? "已启用" : "已停用"}
                  />
                </TableCell>
                <TableCell className="tabular-nums">{card.run_count}</TableCell>
                <TableCell className="tabular-nums">
                  {card.allocated_count}
                </TableCell>
                <TableCell className="tabular-nums">
                  {card.created_count}
                </TableCell>
                <TableCell className="tabular-nums">
                  {card.failed_count}
                </TableCell>
                <TableCell className="tabular-nums">
                  {usage.error ? "-" : (usage.charged ?? "-")}
                </TableCell>
                <TableCell className="tabular-nums">
                  {usage.error ? "-" : (usage.pending ?? "-")}
                </TableCell>
                <TableCell
                  className={usage.error ? "text-destructive" : "tabular-nums"}
                  title={usage.error ?? undefined}
                >
                  {usage.error ? "查询失败" : (usage.remaining ?? "-")}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {formatBeijingDateTime(card.usage_checked_at)}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    aria-label={card.active ? "停用卡密" : "启用卡密"}
                    disabled={pending}
                    onClick={() =>
                      onToggle(
                        card.active
                          ? BulkCardAction.deactivate
                          : BulkCardAction.activate,
                        card.id
                      )
                    }
                    size="icon-sm"
                    title={card.active ? "停用" : "启用"}
                    variant="ghost"
                  >
                    {card.active ? <PowerOff /> : <Power />}
                  </Button>
                  <Button
                    aria-label="删除卡密"
                    onClick={() => onDelete(card.id)}
                    size="icon-sm"
                    title="删除"
                    variant="ghost"
                  >
                    <Trash2 />
                  </Button>
                </TableCell>
              </TableRow>
            )
          })}
          {error && (
            <TableRow>
              <TableCell
                className="h-52 text-center text-sm text-destructive"
                colSpan={12}
              >
                无法读取卡密库存
              </TableCell>
            </TableRow>
          )}
          {!loading && !error && !rows.length && (
            <TableRow>
              <TableCell className="h-52 text-center" colSpan={12}>
                <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                <p className="text-sm font-medium">暂无卡密</p>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
