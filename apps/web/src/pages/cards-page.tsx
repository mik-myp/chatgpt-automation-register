import { useDeferredValue, useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  Inbox,
  KeyRound,
  Power,
  PowerOff,
  Search,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"

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
import {
  BulkCardAction,
  type CardUsageItem,
  useBulkCardActionApiKakaoCardsBatchPost,
  useGetCardStatsApiKakaoCardsStatsGet,
  useImportCardsApiKakaoCardsImportPost,
  useListCardsApiKakaoCardsGet,
} from "@/api/generated"
import { ApiError, apiRequest } from "@/lib/api-client"
import { TablePagination } from "@/components/table-pagination"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
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
import { Textarea } from "@workspace/ui/components/textarea"

function refreshCards(queryClient: ReturnType<typeof useQueryClient>) {
  return queryClient.invalidateQueries({
    predicate: (query) =>
      typeof query.queryKey[0] === "string" &&
      query.queryKey[0].startsWith("/api/kakao/cards"),
  })
}

function ImportCardsDialog({
  open,
  setOpen,
}: {
  open: boolean
  setOpen: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [text, setText] = useState("")
  const mutation = useImportCardsApiKakaoCardsImportPost<ApiError>({
    mutation: {
      onSuccess: (result) => {
        void refreshCards(queryClient)
        setOpen(false)
        setName("")
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
            新卡密会归入同一批次，重复内容自动跳过。
          </DialogDescription>
        </DialogHeader>
        <Input
          aria-label="批次名称"
          maxLength={128}
          onChange={(event) => setName(event.target.value)}
          placeholder="批次名称（可选）"
          value={name}
        />
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
            onClick={() =>
              mutation.mutate({ data: { text, batch_name: name } })
            }
          >
            <Upload />
            {mutation.isPending ? "正在导入" : "导入卡密"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CardsPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [state, setState] = useState<"all" | "active" | "inactive">("all")
  const [selected, setSelected] = useState<string[]>([])
  const [importOpen, setImportOpen] = useState(false)
  const [deleteIds, setDeleteIds] = useState<string[]>([])
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(50)
  const deferredSearch = useDeferredValue(search.trim())
  const cards = useListCardsApiKakaoCardsGet({
    search: deferredSearch || undefined,
    active: state === "all" ? undefined : state === "active",
    limit: pageSize,
    offset: page * pageSize,
  })
  const stats = useGetCardStatsApiKakaoCardsStatsGet()
  const mutation = useBulkCardActionApiKakaoCardsBatchPost<ApiError>({
    mutation: {
      onSuccess: (result, variables) => {
        void refreshCards(queryClient)
        setSelected([])
        const action =
          variables.data.action === BulkCardAction.activate
            ? "启用"
            : variables.data.action === BulkCardAction.deactivate
              ? "停用"
              : "删除"
        const skipped = result.skipped ? `，跳过 ${result.skipped}` : ""
        toast.success(`${action}完成：处理 ${result.processed}${skipped}`)
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const usageQuery = useQuery<{ items: CardUsageItem[] }, ApiError>({
    queryKey: ["card-usage-cache"],
    queryFn: () =>
      apiRequest<{ items: CardUsageItem[] }>("/api/kakao/cards/usage", {
        timeout: 300_000,
      }),
    staleTime: 60_000,
    refetchOnMount: true,
  })
  useEffect(() => {
    if (!usageQuery.dataUpdatedAt) return
    void queryClient.invalidateQueries({ queryKey: ["/api/kakao/cards"] })
  }, [queryClient, usageQuery.dataUpdatedAt])
  useEffect(() => {
    if (usageQuery.error) toast.error(usageQuery.error.message)
  }, [usageQuery.error])
  const rows = cards.data?.items ?? []
  const total = cards.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const ids = rows.map((card) => card.id)
  const selectedCount = ids.filter((id) => selected.includes(id)).length
  const usageByCard = new Map(
    (usageQuery.data?.items ?? []).map((item) => [item.card_id, item])
  )
  const run = (action: BulkCardAction) =>
    mutation.mutate({ data: { action, card_ids: selected } })
  const runOne = (action: BulkCardAction, cardId: string) =>
    mutation.mutate({ data: { action, card_ids: [cardId] } })

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">卡密库存</h1>
        <Button onClick={() => setImportOpen(true)}>
          <Upload />
          导入卡密
        </Button>
      </div>
      <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-4">
        {[
          ["总卡密", stats.data?.total ?? 0],
          ["已启用", stats.data?.active ?? 0],
          ["已停用", stats.data?.inactive ?? 0],
          ["批次", stats.data?.batches ?? 0],
        ].map(([label, value], index) => (
          <div className={`px-4 py-4 ${index ? "border-l" : ""}`} key={label}>
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {value}
            </div>
          </div>
        ))}
      </div>
      <section
        aria-label="卡密列表"
        className="flex min-h-0 min-w-0 flex-1 flex-col"
      >
        <div className="flex flex-wrap items-center gap-2 border-b pb-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="搜索卡密"
              className="pl-8"
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(0)
                setSelected([])
              }}
              placeholder="搜索卡密或批次"
              value={search}
            />
          </div>
          <Select
            value={state}
            onValueChange={(value) => {
              setState(value as typeof state)
              setPage(0)
              setSelected([])
            }}
          >
            <SelectTrigger aria-label="卡密状态" className="w-30">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="active">已启用</SelectItem>
              <SelectItem value="inactive">已停用</SelectItem>
            </SelectContent>
          </Select>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
            {selected.length > 0 && (
              <>
                <span className="text-xs font-medium">
                  已选 {selected.length} 项
                </span>
                <Button
                  disabled={mutation.isPending}
                  onClick={() => run(BulkCardAction.activate)}
                  size="sm"
                  variant="outline"
                >
                  <CheckCircle2 />
                  启用
                </Button>
                <Button
                  disabled={mutation.isPending}
                  onClick={() => run(BulkCardAction.deactivate)}
                  size="sm"
                  variant="outline"
                >
                  <XCircle />
                  停用
                </Button>
                <Button
                  onClick={() => setDeleteIds(selected)}
                  size="sm"
                  variant="destructive"
                >
                  <Trash2 />
                  删除
                </Button>
                <Button
                  aria-label="清除选择"
                  onClick={() => setSelected([])}
                  size="icon-sm"
                  variant="ghost"
                >
                  <XCircle />
                </Button>
              </>
            )}
            <Button
              disabled={usageQuery.isFetching}
              onClick={() => void usageQuery.refetch()}
              size="sm"
              variant="outline"
            >
              <KeyRound />
              {usageQuery.isFetching ? "正在查询" : "检查卡密用量"}
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Table className="min-w-220">
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
                    onCheckedChange={(checked) =>
                      setSelected(checked ? ids : [])
                    }
                  />
                </TableHead>
                <TableHead>卡密</TableHead>
                <TableHead>批次</TableHead>
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
                const liveUsage = usageByCard.get(card.id)
                const usage = liveUsage ?? {
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
                    <TableCell className="font-mono text-xs">
                      {card.code}
                    </TableCell>
                    <TableCell className="text-xs">{card.batch_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {card.active ? "已启用" : "已停用"}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {card.run_count}
                    </TableCell>
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
                      {usage?.error ? "-" : (usage?.charged ?? "-")}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {usage?.error ? "-" : (usage?.pending ?? "-")}
                    </TableCell>
                    <TableCell
                      className={
                        usage?.error ? "text-destructive" : "tabular-nums"
                      }
                      title={usage?.error ?? undefined}
                    >
                      {usage?.error ? "查询失败" : (usage?.remaining ?? "-")}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {card.usage_checked_at
                        ? new Date(card.usage_checked_at).toLocaleString(
                            "zh-CN"
                          )
                        : "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        aria-label={card.active ? "停用卡密" : "启用卡密"}
                        disabled={mutation.isPending}
                        onClick={() =>
                          runOne(
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
                        onClick={() => setDeleteIds([card.id])}
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
              {cards.isError && (
                <TableRow>
                  <TableCell
                    className="h-52 text-center text-sm text-destructive"
                    colSpan={13}
                  >
                    无法读取卡密库存
                  </TableCell>
                </TableRow>
              )}
              {!cards.isLoading && !cards.isError && !rows.length && (
                <TableRow>
                  <TableCell className="h-52 text-center" colSpan={13}>
                    <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                    <p className="text-sm font-medium">暂无卡密</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <TablePagination
          page={page}
          pageCount={pageCount}
          pageSize={pageSize}
          onPageChange={(value) => {
            setPage(value)
            setSelected([])
          }}
          onPageSizeChange={(value) => {
            setPageSize(value)
            setPage(0)
            setSelected([])
          }}
        />
      </section>
      <ImportCardsDialog open={importOpen} setOpen={setImportOpen} />
      <AlertDialog
        open={deleteIds.length > 0}
        onOpenChange={(open) => !open && setDeleteIds([])}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              删除 {deleteIds.length} 个卡密？
            </AlertDialogTitle>
            <AlertDialogDescription>
              已被流水线或 Kakao 任务引用的卡密会自动跳过。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                mutation.mutate({
                  data: { action: BulkCardAction.delete, card_ids: deleteIds },
                })
                setDeleteIds([])
              }}
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
