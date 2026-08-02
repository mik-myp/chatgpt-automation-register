import { useDeferredValue, useState } from "react"
import { useNavigate } from "react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CreditCard, Search } from "lucide-react"
import { toast } from "sonner"

import {
  type CardSelectionResponse,
  type KakaoPipelineCandidateList,
  type KakaoPipelineCandidatePage,
  type PipelineRunSummary,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { ApiError, apiRequest } from "@/lib/api-client"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
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
  DialogTrigger,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

const ELIGIBILITY_LABELS: Record<string, string> = {
  eligible: "可创建",
  ineligible: "不可创建",
  not_eligible: "不可创建",
  invalid_token: "令牌失效",
  forbidden: "无权限",
  rate_limited: "请求受限",
  unknown: "待检查",
}

export function CreateKakaoPipelineDialog({
  sourceRunId,
  iconOnly = false,
}: {
  sourceRunId?: string
  iconOnly?: boolean
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [selectedEmails, setSelectedEmails] = useState<string[] | null>(null)
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)
  const deferredSearch = useDeferredValue(search.trim())
  const pageSize = 50
  const candidateParams = {
    search: deferredSearch || undefined,
    limit: pageSize,
    offset: page * pageSize,
  }
  const candidates = useQuery<
    KakaoPipelineCandidateList | KakaoPipelineCandidatePage,
    ApiError
  >({
    queryKey: sourceRunId
      ? ["/api/pipelines/runs", sourceRunId, "kakao-candidates"]
      : ["/api/pipelines/runs/kakao-candidates", candidateParams],
    queryFn: () =>
      sourceRunId
        ? apiRequest<KakaoPipelineCandidateList>(
            `/api/pipelines/runs/${encodeURIComponent(sourceRunId)}/kakao-candidates`
          )
        : apiRequest<KakaoPipelineCandidatePage>(
            "/api/pipelines/runs/kakao-candidates",
            { params: candidateParams }
          ),
    enabled: open,
  })
  const allRows = candidates.data?.items ?? []
  const rows = sourceRunId
    ? allRows.slice(page * pageSize, (page + 1) * pageSize)
    : allRows
  const allEmails = allRows.map((item) => item.email)
  const pageEmails = rows.map((item) => item.email)
  const selected = selectedEmails ?? (sourceRunId ? allEmails : [])
  const selectedOnPage = pageEmails.filter((email) =>
    selected.includes(email)
  ).length
  const allSelected = rows.length > 0 && selectedOnPage === rows.length
  const total =
    candidates.data && "total" in candidates.data
      ? candidates.data.total
      : allRows.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const capacity = useQuery<CardSelectionResponse, ApiError>({
    queryKey: ["/api/kakao/cards/select", selected.length],
    queryFn: () =>
      apiRequest<CardSelectionResponse>("/api/kakao/cards/select", {
        method: "POST",
        data: { target_count: selected.length },
      }),
    enabled: open && selected.length > 0,
    retry: false,
    refetchOnWindowFocus: false,
  })
  const mutation = useMutation<
    PipelineRunSummary,
    ApiError,
    { emails: string[] }
  >({
    mutationFn: (data) =>
      apiRequest(
        sourceRunId
          ? `/api/pipelines/runs/${encodeURIComponent(sourceRunId)}/kakao-runs`
          : "/api/pipelines/runs/kakao-runs",
        { method: "POST", data }
      ),
    onSuccess: (run) => {
      setOpen(false)
      void queryClient.invalidateQueries({ queryKey: ["/api/pipelines/runs"] })
      void queryClient.invalidateQueries({ queryKey: ["/api/kakao/cards"] })
      toast.success(`已创建 Kakao 流水线 ${run.id.slice(0, 8)}`)
      void navigate(`/pipelines/${run.id}`)
    },
    onError: (error) => toast.error(error.message),
  })
  const setDialogOpen = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) {
      setSelectedEmails(null)
      setSearch("")
      setPage(0)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setDialogOpen}>
      <DialogTrigger asChild>
        <Button
          aria-label={iconOnly ? "创建 Kakao 流水线" : undefined}
          size={iconOnly ? "icon-sm" : sourceRunId ? "sm" : "default"}
          title={iconOnly ? "创建 Kakao 流水线" : undefined}
          variant="outline"
        >
          <CreditCard />
          {!iconOnly && "创建 Kakao"}
        </Button>
      </DialogTrigger>
      <DialogContent className="flex h-[min(42rem,calc(100svh-2rem))] min-h-0 flex-col overflow-hidden sm:max-w-3xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>创建 Kakao 流水线</DialogTitle>
          <DialogDescription>
            {sourceRunId
              ? "选择该注册轮次中已有 Access Token 的账号。"
              : "从注册结果中选择账号，系统会校验卡密容量后创建轮次。"}
          </DialogDescription>
        </DialogHeader>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          {!sourceRunId && (
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="搜索 Kakao 候选邮箱"
                className="pl-8"
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(0)
                }}
                placeholder="搜索邮箱"
                value={search}
              />
            </div>
          )}
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            可选 {total} 个，已选 {selected.length} 个
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto border-y">
          <Table className="min-w-160">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    aria-label="选择当前页全部 Kakao 候选账号"
                    checked={
                      allSelected
                        ? true
                        : selectedOnPage > 0
                          ? "indeterminate"
                          : false
                    }
                    onCheckedChange={(checked) => {
                      const pageSet = new Set(pageEmails)
                      setSelectedEmails(
                        checked
                          ? [...new Set([...selected, ...pageEmails])]
                          : selected.filter((email) => !pageSet.has(email))
                      )
                    }}
                  />
                </TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>最近资格</TableHead>
                <TableHead>检查时间</TableHead>
                <TableHead>说明</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => {
                const state = item.eligibility_state || "unknown"
                return (
                  <TableRow key={item.email}>
                    <TableCell>
                      <Checkbox
                        aria-label={`选择 ${item.email}`}
                        checked={selected.includes(item.email)}
                        onCheckedChange={() =>
                          setSelectedEmails(
                            selected.includes(item.email)
                              ? selected.filter((email) => email !== item.email)
                              : [...selected, item.email]
                          )
                        }
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {item.email}
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={state}
                        label={ELIGIBILITY_LABELS[state] ?? state}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {item.eligibility_checked_at
                        ? formatCompactBeijingDateTime(
                            item.eligibility_checked_at
                          )
                        : "-"}
                    </TableCell>
                    <TableCell className="max-w-52 truncate text-xs text-muted-foreground">
                      {item.eligibility_error || "-"}
                    </TableCell>
                  </TableRow>
                )
              })}
              {!candidates.isLoading && !rows.length && (
                <TableRow>
                  <TableCell className="h-44 text-center" colSpan={5}>
                    <p className="text-sm font-medium">暂无可创建账号</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      账号需要有效的 Access Token，且不能正在其他 Kakao 轮次中或已生成过支付链接。
                    </p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className="shrink-0">
          <TablePagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPageChange={setPage}
          />
        </div>
        <DialogFooter className="shrink-0 sm:items-center">
          <div className="mr-auto min-w-0 text-xs break-words sm:max-w-md">
            {selected.length === 0 ? (
              <span className="text-muted-foreground">请选择账号</span>
            ) : capacity.isFetching ? (
              <span className="text-muted-foreground">
                正在校验 {selected.length} 个卡密名额...
              </span>
            ) : capacity.isError ? (
              <span className="text-destructive">{capacity.error.message}</span>
            ) : (
              <span className="text-emerald-700 dark:text-emerald-300">
                已确认 {selected.length} 个卡密名额
              </span>
            )}
          </div>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={
              !selected.length ||
              capacity.isFetching ||
              capacity.isError ||
              mutation.isPending
            }
            onClick={() => mutation.mutate({ emails: selected })}
          >
            <CreditCard />
            创建 Kakao 流水线（{selected.length}）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
