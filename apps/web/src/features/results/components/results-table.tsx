import { useState } from "react"
import { useSearchParams } from "react-router"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Download,
  Eye,
  Inbox,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react"
import { toast } from "sonner"

import {
  ListResultsApiResultsGetTokenFilter,
  type RegistrationResultDetail,
  type ResultOperationSummary,
  useDeleteResultsApiResultsBatchDeletePost,
  useExportResultsApiResultsExportPost,
  useListResultsApiResultsGet,
} from "@/api/generated"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import { ResultDetailDialog } from "@/features/results/components/result-detail-dialog"
import {
  PlusState,
  SecurityState,
  TokenState,
} from "@/features/results/components/result-details"
import { downloadResultsJson } from "@/features/results/lib/result-actions"
import { runResultOperation } from "@/features/results/lib/result-operations"
import { resultsRouteState } from "@/features/results/lib/results-route-state"
import { ApiError, apiRequest } from "@/lib/api-client"
import { formatBeijingDateTime } from "@/lib/date-time"
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
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
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

export function ResultsTable() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const { search, filter, page, pageSize, params } =
    resultsRouteState(searchParams)
  const [selected, setSelected] = useState<string[]>([])
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const results = useListResultsApiResultsGet(params)
  const rows = results.data?.items ?? []
  const emails = rows.map((item) => item.email)
  const selectedOnPage = emails.filter((email) =>
    selected.includes(email)
  ).length
  const pageCount = Math.max(
    1,
    Math.ceil((results.data?.total ?? 0) / pageSize)
  )

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
        setSelected([])
        setDeleteOpen(false)
        toast.success(`已删除 ${data.processed} 条注册结果`)
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const detailMutation = useMutation<
    RegistrationResultDetail,
    ApiError,
    string
  >({
    mutationFn: (email) =>
      apiRequest<RegistrationResultDetail>(
        `/api/results/${encodeURIComponent(email)}`
      ),
    onSuccess: () => setDetailOpen(true),
    onError: (error) => toast.error(error.message),
  })
  const plusMutation = useMutation<ResultOperationSummary, ApiError, void>({
    mutationFn: () =>
      runResultOperation("/api/results/check-plus", {
        emails: selected,
        all: false,
      }),
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
        emails: selected,
        all: false,
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
    <>
      <section
        aria-label="注册结果列表"
        className="flex min-h-0 min-w-0 flex-1 flex-col border-t"
      >
        <div
          className="flex flex-wrap items-center gap-2 border-b py-3"
          id={TOUR_IDS.resultsList}
        >
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="搜索注册邮箱"
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
              placeholder="搜索邮箱"
              value={search}
            />
          </div>
          <Select
            value={filter}
            onValueChange={(value) => {
              setSearchParams((current) => {
                const next = new URLSearchParams(current)
                if (value === ListResultsApiResultsGetTokenFilter.all)
                  next.delete("filter")
                else next.set("filter", value)
                next.delete("page")
                return next
              })
              setSelected([])
            }}
          >
            <SelectTrigger aria-label="令牌筛选" className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部结果</SelectItem>
              <SelectItem value="access">有 Access Token</SelectItem>
              <SelectItem value="session">有 Session Token</SelectItem>
              <SelectItem value="refresh">有 Refresh Token</SelectItem>
              <SelectItem value="plus">确认是 Plus</SelectItem>
              <SelectItem value="not_plus">确认非 Plus</SelectItem>
              <SelectItem value="plus_unknown">Plus 无法确认</SelectItem>
            </SelectContent>
          </Select>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
            {selected.length > 0 && (
              <>
                <span className="text-xs font-medium">
                  已选 {selected.length} 项
                </span>
                <Button
                  onClick={() =>
                    exportMutation.mutate({
                      data: { emails: selected, all: false },
                    })
                  }
                  size="sm"
                  variant="outline"
                >
                  <Download />
                  导出选中
                </Button>
                <Button
                  disabled={plusMutation.isPending}
                  onClick={() => plusMutation.mutate()}
                  size="sm"
                  variant="outline"
                >
                  <ShieldCheck />
                  严格检查 Plus
                </Button>
                <Button
                  disabled={publishMutation.isPending}
                  onClick={() => publishMutation.mutate("cpa")}
                  size="sm"
                  variant="outline"
                >
                  <Send />
                  CPA
                </Button>
                <Button
                  disabled={publishMutation.isPending}
                  onClick={() => publishMutation.mutate("sub2api")}
                  size="sm"
                  variant="outline"
                >
                  <Send />
                  SUB2API
                </Button>
                <Button
                  onClick={() => setDeleteOpen(true)}
                  size="sm"
                  variant="destructive"
                >
                  <Trash2 />
                  删除选中
                </Button>
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
              isRefreshing={results.isFetching}
              label="刷新注册结果"
              onRefresh={() => void results.refetch()}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Table className="min-w-190">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    aria-label="选择当前页全部结果"
                    checked={
                      emails.length > 0 && selectedOnPage === emails.length
                        ? true
                        : selectedOnPage > 0
                          ? "indeterminate"
                          : false
                    }
                    onCheckedChange={(checked) =>
                      setSelected(checked ? emails : [])
                    }
                  />
                </TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>密码</TableHead>
                <TableHead>MFA</TableHead>
                <TableHead>Access</TableHead>
                <TableHead>Session</TableHead>
                <TableHead>Refresh</TableHead>
                <TableHead>Plus</TableHead>
                <TableHead>保存时间</TableHead>
                <TableHead className="w-14 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <TableRow key={item.email}>
                  <TableCell>
                    <Checkbox
                      aria-label={`选择 ${item.email}`}
                      checked={selected.includes(item.email)}
                      onCheckedChange={() =>
                        setSelected(
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
                    <SecurityState
                      kind="password"
                      value={item.chatgpt_password}
                      status={
                        item.password_status ??
                        (item.has_password ? "available" : null)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <SecurityState
                      kind="mfa"
                      status={item.mfa_status}
                      value={item.totp_secret}
                    />
                  </TableCell>
                  <TableCell>
                    <TokenState value={item.has_access_token} />
                  </TableCell>
                  <TableCell>
                    <TokenState value={item.has_session_token} />
                  </TableCell>
                  <TableCell>
                    <TokenState value={item.has_refresh_token} />
                  </TableCell>
                  <TableCell>
                    <PlusState
                      state={item.plus_state}
                      label={item.plus_label}
                      error={item.plus_error}
                      checkedAt={item.plus_checked_at}
                      planType={item.plus_plan_type}
                      subscriptionPlan={item.plus_subscription_plan}
                      activeSubscription={item.plus_has_active_subscription}
                      expiresAt={item.plus_expires_at}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {formatBeijingDateTime(item.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      aria-label={`查看 ${item.email} 凭证`}
                      onClick={() => detailMutation.mutate(item.email)}
                      size="icon-sm"
                      variant="ghost"
                    >
                      <Eye />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!results.isLoading && !rows.length && (
                <TableRow>
                  <TableCell className="h-52 text-center" colSpan={10}>
                    <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                    <Badge variant="outline">暂无注册结果</Badge>
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
          total={results.data?.total ?? 0}
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
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              删除选中的 {selected.length} 条结果？
            </AlertDialogTitle>
            <AlertDialogDescription>
              凭证和令牌将永久删除，号池账号不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                deleteMutation.mutate({
                  data: { emails: selected, all: false },
                })
              }
              variant="destructive"
            >
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <ResultDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        result={detailMutation.data}
      />
    </>
  )
}
