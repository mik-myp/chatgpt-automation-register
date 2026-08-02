import { useDeferredValue, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  CreditCard,
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
  useDeleteResultsApiResultsBatchDeletePost,
  useExportResultsApiResultsExportPost,
  useListResultsApiResultsGet,
} from "@/api/generated"
import { TablePagination } from "@/components/table-pagination"
import { TableRefreshButton } from "@/components/table-refresh-button"
import {
  PlusState,
  SecurityState,
  TokenState,
} from "@/features/results/components/result-details"
import { ResultDetailDialog } from "@/features/results/components/result-detail-dialog"
import {
  downloadResultsJson,
  type StrictPlusCheckResponse,
} from "@/features/results/lib/result-actions"
import { ApiError, apiRequest } from "@/lib/api-client"
import { formatBeijingDateTime } from "@/lib/date-time"
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

export function ResultsPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState(ListResultsApiResultsGetTokenFilter.all)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(50)
  const [selected, setSelected] = useState<string[]>([])
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteAll, setDeleteAll] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const deferredSearch = useDeferredValue(search.trim())
  const results = useListResultsApiResultsGet({
    search: deferredSearch || undefined,
    token_filter: filter,
    limit: pageSize,
    offset: page * pageSize,
  })
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
        setDeleteAll(false)
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
  const plusMutation = useMutation<StrictPlusCheckResponse, ApiError, boolean>({
    mutationFn: (all) =>
      apiRequest<StrictPlusCheckResponse>("/api/results/check-plus", {
        method: "POST",
        data: { emails: all ? [] : selected, all },
        timeout: 600_000,
      }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["/api/results"] })
      const plus = data.items.filter((item) => item.is_plus === true).length
      const unknown = data.items.filter((item) => item.is_plus == null).length
      toast.success(
        `Plus 检查完成：确认 Plus ${plus}/${data.items.length}${unknown ? `，无法确认 ${unknown}` : ""}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const kakaoMutation = useMutation<
    { created: number; duplicates: number },
    ApiError,
    void
  >({
    mutationFn: () =>
      apiRequest<{ created: number; duplicates: number }>(
        "/api/kakao/tasks/create",
        {
          method: "POST",
          data: { emails: selected },
        }
      ),
    onSuccess: (data) =>
      toast.success(
        `Kakao 任务已创建 ${data.created} 个，重复 ${data.duplicates} 个`
      ),
    onError: (error) => toast.error(error.message),
  })
  const publishMutation = useMutation<
    { processed: number; succeeded: number; failed: number; errors: string[] },
    ApiError,
    { target: "cpa" | "sub2api"; all: boolean }
  >({
    mutationFn: ({ target, all }) =>
      apiRequest<{
        processed: number
        succeeded: number
        failed: number
        errors: string[]
      }>("/api/results/publish", {
        method: "POST",
        data: { emails: all ? [] : selected, all, targets: [target] },
        timeout: 3_600_000,
      }),
    onSuccess: (data, { target }) => {
      if (data.failed)
        toast.error(`${target.toUpperCase()} 发布失败 ${data.failed} 条`)
      else toast.success(`${target.toUpperCase()} 已发布 ${data.succeeded} 条`)
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">注册结果</h1>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <Button
            disabled={plusMutation.isPending}
            onClick={() => plusMutation.mutate(true)}
            size="sm"
            variant="outline"
          >
            <ShieldCheck />
            严格检查全部 Plus
          </Button>
          <Button
            disabled={publishMutation.isPending}
            onClick={() => publishMutation.mutate({ target: "cpa", all: true })}
            size="sm"
            variant="outline"
          >
            <Send />
            全部到 CPA
          </Button>
          <Button
            disabled={publishMutation.isPending}
            onClick={() =>
              publishMutation.mutate({ target: "sub2api", all: true })
            }
            size="sm"
            variant="outline"
          >
            <Send />
            全部到 SUB2API
          </Button>
          <Button
            onClick={() =>
              exportMutation.mutate({ data: { all: true, emails: [] } })
            }
            size="sm"
            variant="outline"
          >
            <Download />
            导出全部
          </Button>
          <Button
            onClick={() => {
              setDeleteAll(true)
              setDeleteOpen(true)
            }}
            size="sm"
            variant="destructive"
          >
            <Trash2 />
            删除全部
          </Button>
        </div>
      </div>
      <section
        aria-label="注册结果列表"
        className="flex min-h-0 min-w-0 flex-1 flex-col border-t"
      >
        <div className="flex flex-wrap items-center gap-2 border-b py-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="搜索注册邮箱"
              className="pl-8"
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(0)
                setSelected([])
              }}
              placeholder="搜索邮箱"
              value={search}
            />
          </div>
          <Select
            value={filter}
            onValueChange={(value) => {
              setFilter(value as typeof filter)
              setPage(0)
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
                  onClick={() => plusMutation.mutate(false)}
                  size="sm"
                  variant="outline"
                >
                  <ShieldCheck />
                  严格检查 Plus
                </Button>
                <Button
                  disabled={kakaoMutation.isPending}
                  onClick={() => kakaoMutation.mutate()}
                  size="sm"
                  variant="outline"
                >
                  <CreditCard />
                  创建 Kakao
                </Button>
                <Button
                  disabled={publishMutation.isPending}
                  onClick={() =>
                    publishMutation.mutate({ target: "cpa", all: false })
                  }
                  size="sm"
                  variant="outline"
                >
                  <Send />
                  CPA
                </Button>
                <Button
                  disabled={publishMutation.isPending}
                  onClick={() =>
                    publishMutation.mutate({ target: "sub2api", all: false })
                  }
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
      <AlertDialog
        open={deleteOpen}
        onOpenChange={(open) => {
          setDeleteOpen(open)
          if (!open) setDeleteAll(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {deleteAll
                ? "删除全部注册结果？"
                : `删除选中的 ${selected.length} 条结果？`}
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
                  data: {
                    emails: deleteAll ? [] : selected,
                    all: deleteAll,
                  },
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
    </div>
  )
}
