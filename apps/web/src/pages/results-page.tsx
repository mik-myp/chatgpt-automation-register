import { useDeferredValue, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Check,
  Clipboard,
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
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import { Input } from "@workspace/ui/components/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
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

function downloadJson(value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `registration-results-${new Date().toISOString().slice(0, 10)}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

function TokenState({ value }: { value: boolean }) {
  return value ? (
    <Check className="size-4 text-emerald-600" />
  ) : (
    <span className="text-muted-foreground">-</span>
  )
}

function PlusState({
  eligible,
  state,
  error,
  checkedAt,
}: {
  eligible?: boolean | null
  state?: string | null
  error?: string | null
  checkedAt?: string | null
}) {
  const labels: Record<string, string> = {
    plus_active: "Plus 生效中",
    plus_eligible: "可领 Plus",
    free: "Free",
    banned: "封号",
    error: "检查失败",
    no_at: "无 Access Token",
  }
  if (eligible == null && !state)
    return <span className="text-xs text-muted-foreground">未检查</span>
  return (
    <Badge
      title={[
        state,
        error,
        checkedAt ? new Date(checkedAt).toLocaleString("zh-CN") : "",
      ]
        .filter(Boolean)
        .join("\n")}
      variant="outline"
    >
      {labels[state ?? ""] ?? (eligible ? "可用" : "不可用")}
    </Badge>
  )
}

function CredentialField({
  label,
  value,
}: {
  label: string
  value?: string | null
}) {
  return (
    <div className="grid gap-1.5 border-b py-3 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium">{label}</span>
        <Button
          aria-label={`复制${label}`}
          disabled={!value}
          onClick={() => {
            void navigator.clipboard.writeText(value ?? "")
            toast.success(`已复制${label}`)
          }}
          size="icon-sm"
          variant="ghost"
        >
          <Clipboard />
        </Button>
      </div>
      <pre className="max-h-28 overflow-auto rounded-sm bg-muted/40 p-2 font-mono text-xs break-all whitespace-pre-wrap">
        {value || "-"}
      </pre>
    </div>
  )
}

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
        downloadJson(data.items)
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
  const eligibilityMutation = useMutation<
    {
      items: Array<{
        email: string
        eligible: boolean | null
        status: string
        label: string
        error: string
      }>
    },
    ApiError,
    boolean
  >({
    mutationFn: (all) =>
      apiRequest<{
        items: Array<{
          email: string
          eligible: boolean | null
          status: string
          label: string
          error: string
        }>
      }>("/api/results/check-plus", {
        method: "POST",
        data: { emails: all ? [] : selected, all },
        timeout: 600_000,
      }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["/api/results"] })
      const eligible = data.items.filter((item) => item.eligible).length
      const failed = data.items.filter((item) => item.error).length
      toast.success(
        `Plus 检查完成：${eligible}/${data.items.length} 个账号可用${failed ? `，${failed} 个失败` : ""}`
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
            disabled={eligibilityMutation.isPending}
            onClick={() => eligibilityMutation.mutate(true)}
            size="sm"
            variant="outline"
          >
            <ShieldCheck />
            检查全部 Plus
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
              <SelectItem value="plus_eligible">Plus 可用</SelectItem>
              <SelectItem value="plus_ineligible">Plus 不可用</SelectItem>
              <SelectItem value="plus_unchecked">Plus 未检查</SelectItem>
            </SelectContent>
          </Select>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
            <span className="text-xs text-muted-foreground">
              筛选结果 {results.data?.total ?? 0} 条
            </span>
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
                  disabled={eligibilityMutation.isPending}
                  onClick={() => eligibilityMutation.mutate(false)}
                  size="sm"
                  variant="outline"
                >
                  <ShieldCheck />
                  检查 Plus
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
                <TableHead>Access</TableHead>
                <TableHead>Session</TableHead>
                <TableHead>Refresh</TableHead>
                <TableHead>Plus 资格</TableHead>
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
                    <TokenState value={item.has_password} />
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
                      checkedAt={item.plus_checked_at}
                      eligible={item.plus_eligible}
                      error={item.plus_error}
                      state={item.plus_state}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleString("zh-CN")}
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
                  <TableCell className="h-52 text-center" colSpan={9}>
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
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>凭证详情</DialogTitle>
            <DialogDescription>{detailMutation.data?.email}</DialogDescription>
          </DialogHeader>
          {detailMutation.data && (
            <div>
              <div className="flex justify-end border-b pb-2">
                <Button
                  onClick={() => {
                    void navigator.clipboard.writeText(
                      JSON.stringify(detailMutation.data, null, 2)
                    )
                    toast.success("已复制完整凭证 JSON")
                  }}
                  size="sm"
                  variant="outline"
                >
                  <Clipboard />
                  复制 JSON
                </Button>
              </div>
              <CredentialField label="邮箱" value={detailMutation.data.email} />
              <CredentialField
                label="密码"
                value={detailMutation.data.password}
              />
              <CredentialField
                label="Access Token"
                value={detailMutation.data.access_token}
              />
              <CredentialField
                label="Session Token"
                value={detailMutation.data.session_token}
              />
              <CredentialField
                label="Refresh Token"
                value={detailMutation.data.refresh_token}
              />
              <CredentialField
                label="ID Token"
                value={detailMutation.data.id_token}
              />
              <CredentialField
                label="Device ID"
                value={detailMutation.data.device_id}
              />
              <CredentialField
                label="Cookie"
                value={detailMutation.data.cookie_header}
              />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
