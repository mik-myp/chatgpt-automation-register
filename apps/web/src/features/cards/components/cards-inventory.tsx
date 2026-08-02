import { useEffect, useState } from "react"
import { useSearchParams } from "react-router"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, KeyRound, Search, Trash2, XCircle } from "lucide-react"
import { toast } from "sonner"

import {
  BulkCardAction,
  type CardUsageItem,
  useBulkCardActionApiKakaoCardsBatchPost,
  useGetCardStatsApiKakaoCardsStatsGet,
  useListCardsApiKakaoCardsGet,
} from "@/api/generated"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import { CardsTable } from "@/features/cards/components/cards-table"
import { refreshCardQueries } from "@/features/cards/lib/card-queries"
import { cardsRouteState } from "@/features/cards/lib/cards-route-state"
import { ApiError, apiRequest } from "@/lib/api-client"
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
import { Input } from "@workspace/ui/components/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"

export function CardsInventory() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const { search, state, page, pageSize, params } =
    cardsRouteState(searchParams)
  const [selected, setSelected] = useState<string[]>([])
  const [deleteIds, setDeleteIds] = useState<string[]>([])
  const cards = useListCardsApiKakaoCardsGet(params)
  const stats = useGetCardStatsApiKakaoCardsStatsGet()
  const mutation = useBulkCardActionApiKakaoCardsBatchPost<ApiError>({
    mutation: {
      onSuccess: (result, variables) => {
        void refreshCardQueries(queryClient)
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
  const usageByCard = new Map(
    (usageQuery.data?.items ?? []).map((item) => [item.card_id, item])
  )
  const remainingTotal = usageQuery.data
    ? usageQuery.data.items.reduce(
        (sum, item) => sum + (item.error ? 0 : item.remaining),
        0
      )
    : null
  const remainingFailures =
    usageQuery.data?.items.filter((item) => item.error).length ?? 0
  const run = (action: BulkCardAction) =>
    mutation.mutate({ data: { action, card_ids: selected } })

  return (
    <>
      <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-4">
        {[
          ["总卡密", stats.data?.total ?? 0],
          ["已启用", stats.data?.active ?? 0],
          ["已停用", stats.data?.inactive ?? 0],
          ["实时剩余", remainingTotal ?? "-"],
        ].map(([label, value], index) => (
          <div
            className={`px-4 py-4 ${index ? "border-l" : ""}`}
            key={label}
            title={
              label === "实时剩余" && remainingFailures
                ? `${remainingFailures} 个卡密查询失败，当前合计不包含失败项`
                : undefined
            }
          >
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
                setSearchParams(
                  (current) => {
                    const next = new URLSearchParams(current)
                    const value = event.target.value.trim()
                    if (value) next.set("search", value)
                    else next.delete("search")
                    next.delete("page")
                    return next
                  },
                  { replace: true }
                )
                setSelected([])
              }}
              placeholder="搜索卡密"
              value={search}
            />
          </div>
          <Select
            value={state}
            onValueChange={(value) => {
              setSearchParams((current) => {
                const next = new URLSearchParams(current)
                if (value === "all") next.delete("state")
                else next.set("state", value)
                next.delete("page")
                return next
              })
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
            <TableRefreshButton
              isRefreshing={cards.isFetching || stats.isFetching}
              label="刷新卡密列表"
              onRefresh={() => {
                void cards.refetch()
                void stats.refetch()
              }}
            />
          </div>
        </div>
        <CardsTable
          rows={rows}
          usageByCard={usageByCard}
          selected={selected}
          setSelected={setSelected}
          loading={cards.isLoading}
          error={cards.isError}
          pending={mutation.isPending}
          onToggle={(action, cardId) =>
            mutation.mutate({ data: { action, card_ids: [cardId] } })
          }
          onDelete={(cardId) => setDeleteIds([cardId])}
        />
        <TablePagination
          page={page}
          pageCount={pageCount}
          pageSize={pageSize}
          total={cards.data?.total ?? 0}
          onPageChange={(value) => {
            setSearchParams((current) => {
              const next = new URLSearchParams(current)
              if (value === 0) next.delete("page")
              else next.set("page", String(value + 1))
              return next
            })
            setSelected([])
          }}
          onPageSizeChange={(value) => {
            setSearchParams((current) => {
              const next = new URLSearchParams(current)
              if (value === 50) next.delete("page_size")
              else next.set("page_size", String(value))
              next.delete("page")
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
              删除 {deleteIds.length} 个卡密？
            </AlertDialogTitle>
            <AlertDialogDescription>
              仍被排队、运行或暂停中的流水线占用的卡密会自动跳过。历史 Kakao
              任务将保留卡密编号快照。
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
    </>
  )
}
