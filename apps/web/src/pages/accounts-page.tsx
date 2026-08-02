import { useDeferredValue, useState } from "react"
import { useNavigate } from "react-router"
import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import {
  Ellipsis,
  Inbox,
  KeyRound,
  Play,
  RefreshCcw,
  RotateCcw,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react"
import { toast } from "sonner"

import {
  AccountStatus,
  AccountMaintenanceAction,
  type AccountSummary,
  type AccountStats,
  BulkAccountAction,
  getListAccountsApiAccountsGetQueryKey,
  useBulkAccountActionApiAccountsBatchPost,
  useDeleteAccountApiAccountsEmailDelete,
  useGetAccountStatsApiAccountsStatsGet,
  useImportAccountsApiAccountsImportPost,
  useListAccountsApiAccountsGet,
  useMaintainAccountsApiAccountsMaintenancePost,
  useReleaseAccountApiAccountsEmailReleasePost,
  useResetAccountApiAccountsEmailResetPost,
} from "@/api/generated"
import { ApiError } from "@/lib/api-client"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { useAccountsStore } from "@/stores/accounts-store"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@workspace/ui/components/dropdown-menu"
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

const STATUS_LABELS = {
  [AccountStatus.available]: "可用",
  [AccountStatus.in_use]: "使用中",
  [AccountStatus.done]: "已完成",
  [AccountStatus.failed]: "失败",
} as const

const DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
})

function errorMessage(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : "操作失败，请检查本地 API 服务"
}

function refreshAccountQueries(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    predicate: (query) =>
      typeof query.queryKey[0] === "string" &&
      query.queryKey[0].startsWith("/api/accounts"),
  })
}

function formatDate(value: string | null) {
  return value ? DATE_FORMATTER.format(new Date(value)) : "-"
}

function StatusBand({ stats }: { stats?: AccountStats }) {
  const entries = [
    ["总账号", stats?.total ?? 0, "text-foreground"],
    ["可用", stats?.available ?? 0, "text-emerald-600 dark:text-emerald-400"],
    ["使用中", stats?.in_use ?? 0, "text-amber-600 dark:text-amber-400"],
    ["已完成", stats?.done ?? 0, "text-sky-600 dark:text-sky-400"],
    ["失败", stats?.failed ?? 0, "text-red-600 dark:text-red-400"],
  ] as const

  return (
    <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-5">
      {entries.map(([label, value, color], index) => (
        <div
          className={`flex min-h-20 flex-col justify-center px-4 py-3 sm:px-5 ${index ? "border-l" : ""} ${index === 4 ? "col-span-2 border-t sm:col-span-1 sm:border-t-0" : ""}`}
          key={label}
        >
          <span className="text-xs text-muted-foreground">{label}</span>
          <span
            className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${color}`}
          >
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}

function AccountActions({ account }: { account: AccountSummary }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const setDeleteTarget = useAccountsStore((state) => state.setDeleteTarget)
  const release = useReleaseAccountApiAccountsEmailReleasePost<ApiError>({
    mutation: {
      onSuccess: () => {
        toast.success("账号已释放")
        void refreshAccountQueries(queryClient)
      },
      onError: (error) => toast.error(errorMessage(error)),
    },
  })
  const reset = useResetAccountApiAccountsEmailResetPost<ApiError>({
    mutation: {
      onSuccess: () => {
        toast.success("账号已重置为可用")
        void refreshAccountQueries(queryClient)
      },
      onError: (error) => toast.error(errorMessage(error)),
    },
  })
  const busy = release.isPending || reset.isPending

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`管理 ${account.email}`}
          disabled={busy}
          size="icon-sm"
          variant="ghost"
        >
          <Ellipsis />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {account.status === AccountStatus.available && (
          <DropdownMenuItem
            onSelect={() =>
              navigate(`/pipelines?email=${encodeURIComponent(account.email)}`)
            }
          >
            <Play />
            使用账号
          </DropdownMenuItem>
        )}
        {account.status === AccountStatus.in_use && (
          <DropdownMenuItem
            onSelect={() => release.mutate({ email: account.email })}
          >
            <RotateCcw />
            释放账号
          </DropdownMenuItem>
        )}
        {(account.status === AccountStatus.done ||
          account.status === AccountStatus.failed) && (
          <DropdownMenuItem
            onSelect={() => reset.mutate({ email: account.email })}
          >
            <RefreshCcw />
            重置为可用
          </DropdownMenuItem>
        )}
        {account.status !== AccountStatus.in_use && (
          <>
            {(account.status === AccountStatus.done ||
              account.status === AccountStatus.failed) && (
              <DropdownMenuSeparator />
            )}
            <DropdownMenuItem
              variant="destructive"
              onSelect={() => setDeleteTarget(account.email)}
            >
              <Trash2 />
              删除账号
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function AccountMaintenanceActions({
  total,
  status,
}: {
  total: number
  status: AccountStatus | "all"
}) {
  const queryClient = useQueryClient()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const mutation = useMaintainAccountsApiAccountsMaintenancePost<ApiError>({
    mutation: {
      onSuccess: (result, variables) => {
        void refreshAccountQueries(queryClient)
        const labels = {
          [AccountMaintenanceAction.reset_failed]: "重试失败账号",
          [AccountMaintenanceAction.release_stale]: "释放卡死账号",
          [AccountMaintenanceAction.delete_status]: "清理账号",
        }
        const skipped = result.skipped ? `，跳过 ${result.skipped}` : ""
        toast.success(
          `${labels[variables.data.action]}：处理 ${result.processed}${skipped}`
        )
        setDeleteOpen(false)
      },
      onError: (error) => toast.error(errorMessage(error)),
    },
  })
  const run = (action: AccountMaintenanceAction) =>
    mutation.mutate({
      data: {
        action,
        status: status === "all" ? null : status,
        stale_minutes: 30,
      },
    })

  return (
    <>
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        <span className="mr-1 text-xs whitespace-nowrap text-muted-foreground">
          筛选结果 {total} 条
        </span>
        <Button
          aria-label="刷新号池"
          disabled={mutation.isPending}
          onClick={() => void refreshAccountQueries(queryClient)}
          size="icon-sm"
          title="刷新号池"
          variant="outline"
        >
          <RefreshCcw />
        </Button>
        <Button
          disabled={mutation.isPending}
          onClick={() => run(AccountMaintenanceAction.reset_failed)}
          size="sm"
          title="把全部失败账号重置为可用"
          variant="outline"
        >
          <RotateCcw />
          重试失败
        </Button>
        <Button
          disabled={mutation.isPending}
          onClick={() => run(AccountMaintenanceAction.release_stale)}
          size="sm"
          title="释放使用超过 30 分钟的账号"
          variant="outline"
        >
          <RefreshCcw />
          释放卡死
        </Button>
        <Button
          disabled={mutation.isPending || total === 0}
          onClick={() => setDeleteOpen(true)}
          size="sm"
          variant="destructive"
        >
          <Trash2 />
          清理当前筛选
        </Button>
      </div>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>清理当前筛选的 {total} 个账号？</AlertDialogTitle>
            <AlertDialogDescription>
              使用中的账号会被保护并跳过，其余匹配账号将永久删除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => run(AccountMaintenanceAction.delete_status)}
              variant="destructive"
            >
              确认清理
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

function ImportDialog() {
  const queryClient = useQueryClient()
  const [text, setText] = useState("")
  const open = useAccountsStore((state) => state.importOpen)
  const setOpen = useAccountsStore((state) => state.setImportOpen)
  const mutation = useImportAccountsApiAccountsImportPost<ApiError>({
    mutation: {
      onSuccess: (result) => {
        void refreshAccountQueries(queryClient)
        setText("")
        setOpen(false)
        const invalid = result.invalid ? `，无效 ${result.invalid}` : ""
        toast.success(
          `导入完成：新增 ${result.inserted}，更新 ${result.updated}${invalid}`
        )
      },
      onError: (error) => toast.error(errorMessage(error)),
    },
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>导入邮箱账号</DialogTitle>
          <DialogDescription>
            新账号加入可用号池，重复邮箱保留当前状态。
          </DialogDescription>
        </DialogHeader>
        <Textarea
          aria-label="账号文本"
          autoFocus
          className="min-h-72 resize-y font-mono text-xs leading-5"
          onChange={(event) => setText(event.target.value)}
          placeholder={
            "email----password----client_id----refresh_token\nemail---https://mail.example.com/link"
          }
          value={text}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={!text.trim() || mutation.isPending}
            onClick={() => mutation.mutate({ data: { text } })}
          >
            <Upload />
            {mutation.isPending ? "正在导入" : "导入账号"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeleteAccountDialog() {
  const queryClient = useQueryClient()
  const target = useAccountsStore((state) => state.deleteTarget)
  const setTarget = useAccountsStore((state) => state.setDeleteTarget)
  const mutation = useDeleteAccountApiAccountsEmailDelete<ApiError>({
    mutation: {
      onSuccess: () => {
        void refreshAccountQueries(queryClient)
        setTarget(null)
        toast.success("账号已删除")
      },
      onError: (error) => toast.error(errorMessage(error)),
    },
  })

  return (
    <AlertDialog
      open={target !== null}
      onOpenChange={(open) => !open && setTarget(null)}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除这个账号？</AlertDialogTitle>
          <AlertDialogDescription>
            {target} 将从号池永久移除，此操作无法撤销。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction
            disabled={mutation.isPending}
            onClick={() => target && mutation.mutate({ email: target })}
            variant="destructive"
          >
            删除账号
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function BulkAccountActions() {
  const queryClient = useQueryClient()
  const emails = useAccountsStore((state) => state.selectedEmails)
  const clearSelection = useAccountsStore((state) => state.clearSelection)
  const deleteOpen = useAccountsStore((state) => state.bulkDeleteOpen)
  const setDeleteOpen = useAccountsStore((state) => state.setBulkDeleteOpen)
  const mutation = useBulkAccountActionApiAccountsBatchPost<ApiError>({
    mutation: {
      onSuccess: (result, variables) => {
        void refreshAccountQueries(queryClient)
        clearSelection()
        setDeleteOpen(false)
        const labels = {
          [BulkAccountAction.release]: "释放",
          [BulkAccountAction.reset]: "重置",
          [BulkAccountAction.delete]: "删除",
          [BulkAccountAction.set_password]: "修改密码",
          [BulkAccountAction.enable_mfa]: "启用/验证 MFA",
        }
        const skipped = result.skipped ? `，跳过 ${result.skipped}` : ""
        toast.success(
          result.job_id
            ? `${labels[variables.data.action]}已加入后台队列：${result.processed} 个${skipped}`
            : `${labels[variables.data.action]}完成：处理 ${result.processed}${skipped}`
        )
        if (result.job_id) {
          for (const delay of [3000, 10000, 30000]) {
            window.setTimeout(
              () => void refreshAccountQueries(queryClient),
              delay
            )
          }
        }
      },
      onError: (error) => toast.error(errorMessage(error)),
    },
  })
  const run = (action: BulkAccountAction) =>
    mutation.mutate({ data: { action, emails } })

  if (!emails.length) return null

  return (
    <>
      <span className="text-xs font-medium">已选 {emails.length} 项</span>
      <Button
        disabled={mutation.isPending}
        onClick={() => run(BulkAccountAction.set_password)}
        size="sm"
        title="对已选账号执行密码设置；协议不支持时会记录明确状态"
        variant="outline"
      >
        <KeyRound />
        修改密码
      </Button>
      <Button
        disabled={mutation.isPending}
        onClick={() => run(BulkAccountAction.enable_mfa)}
        size="sm"
        variant="outline"
      >
        <ShieldCheck />
        启用/验证 MFA
      </Button>
      <Button
        disabled={mutation.isPending}
        onClick={() => run(BulkAccountAction.release)}
        size="sm"
        variant="outline"
      >
        <RotateCcw />
        释放
      </Button>
      <Button
        disabled={mutation.isPending}
        onClick={() => run(BulkAccountAction.reset)}
        size="sm"
        variant="outline"
      >
        <RefreshCcw />
        重置
      </Button>
      <Button
        disabled={mutation.isPending}
        onClick={() => setDeleteOpen(true)}
        size="sm"
        variant="destructive"
      >
        <Trash2 />
        删除
      </Button>
      <Button
        aria-label="清除选择"
        onClick={clearSelection}
        size="icon-sm"
        variant="ghost"
      >
        <X />
      </Button>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              删除已选的 {emails.length} 个账号？
            </AlertDialogTitle>
            <AlertDialogDescription>
              使用中的账号会被跳过，其余账号将永久移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={mutation.isPending}
              onClick={() => run(BulkAccountAction.delete)}
              variant="destructive"
            >
              批量删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

export function AccountsPage() {
  const search = useAccountsStore((state) => state.search)
  const status = useAccountsStore((state) => state.status)
  const page = useAccountsStore((state) => state.page)
  const pageSize = useAccountsStore((state) => state.pageSize)
  const setSearch = useAccountsStore((state) => state.setSearch)
  const setStatus = useAccountsStore((state) => state.setStatus)
  const setPage = useAccountsStore((state) => state.setPage)
  const setPageSize = useAccountsStore((state) => state.setPageSize)
  const setImportOpen = useAccountsStore((state) => state.setImportOpen)
  const selectedEmails = useAccountsStore((state) => state.selectedEmails)
  const setSelectedEmails = useAccountsStore((state) => state.setSelectedEmails)
  const toggleSelectedEmail = useAccountsStore(
    (state) => state.toggleSelectedEmail
  )
  const deferredSearch = useDeferredValue(search.trim())
  const params = {
    search: deferredSearch || undefined,
    status: status === "all" ? undefined : status,
    limit: pageSize,
    offset: page * pageSize,
  }
  const accounts = useListAccountsApiAccountsGet(params, {
    query: {
      queryKey: getListAccountsApiAccountsGetQueryKey(params),
      placeholderData: (old) => old,
    },
  })
  const stats = useGetAccountStatsApiAccountsStatsGet()
  const total = accounts.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const pageEmails = accounts.data?.items.map((account) => account.email) ?? []
  const selectedOnPage = pageEmails.filter((email) =>
    selectedEmails.includes(email)
  ).length
  const allOnPageSelected =
    pageEmails.length > 0 && selectedOnPage === pageEmails.length

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <h1 className="text-xl font-semibold">邮箱号池</h1>
        <Button onClick={() => setImportOpen(true)}>
          <Upload />
          导入账号
        </Button>
      </div>

      <StatusBand stats={stats.data} />

      <section
        aria-label="账号列表"
        className="flex min-h-0 min-w-0 flex-1 flex-col"
      >
        <div className="flex flex-col gap-2 border-b pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-1 gap-2">
            <div className="relative w-full max-w-sm">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="搜索账号"
                className="pl-8"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索邮箱或失败原因"
                value={search}
              />
            </div>
            <Select
              value={status}
              onValueChange={(value) => setStatus(value as typeof status)}
            >
              <SelectTrigger aria-label="账号状态" className="w-30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value={AccountStatus.available}>可用</SelectItem>
                <SelectItem value={AccountStatus.in_use}>使用中</SelectItem>
                <SelectItem value={AccountStatus.done}>已完成</SelectItem>
                <SelectItem value={AccountStatus.failed}>失败</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
            <AccountMaintenanceActions total={total} status={status} />
            <BulkAccountActions />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          <Table className="min-w-230">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    aria-label="选择当前页全部账号"
                    checked={
                      allOnPageSelected ||
                      (selectedOnPage > 0 ? "indeterminate" : false)
                    }
                    onCheckedChange={(checked) =>
                      setSelectedEmails(checked ? pageEmails : [])
                    }
                  />
                </TableHead>
                <TableHead className="w-[42%]">邮箱</TableHead>
                <TableHead>接收方式</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>密码</TableHead>
                <TableHead>MFA</TableHead>
                <TableHead>领取时间</TableHead>
                <TableHead>完成时间</TableHead>
                <TableHead className="w-10">
                  <span className="sr-only">操作</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {accounts.isLoading &&
                Array.from({ length: 6 }, (_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={9}>
                      <div className="h-5 animate-pulse rounded bg-muted" />
                    </TableCell>
                  </TableRow>
                ))}
              {accounts.isError && (
                <TableRow>
                  <TableCell className="h-52 text-center" colSpan={9}>
                    <p className="text-sm font-medium">无法读取账号池</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {errorMessage(accounts.error)}
                    </p>
                    <Button
                      className="mt-4"
                      onClick={() => accounts.refetch()}
                      size="sm"
                      variant="outline"
                    >
                      <RefreshCcw />
                      重新加载
                    </Button>
                  </TableCell>
                </TableRow>
              )}
              {!accounts.isLoading &&
                accounts.data?.items.map((account) => (
                  <TableRow key={account.email}>
                    <TableCell>
                      <Checkbox
                        aria-label={`选择 ${account.email}`}
                        checked={selectedEmails.includes(account.email)}
                        onCheckedChange={() =>
                          toggleSelectedEmail(account.email)
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <div className="min-w-0">
                        <div className="truncate font-mono text-xs font-medium">
                          {account.email}
                        </div>
                        {account.failure_reason && (
                          <div className="mt-1 max-w-md truncate text-xs text-red-600 dark:text-red-400">
                            {account.failure_reason}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {account.mail_type === "link" ? "邮箱链接" : "OAuth"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={account.status}
                        label={STATUS_LABELS[account.status]}
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={account.password_status}
                        label={
                          {
                            set: "已设置",
                            available: "可用",
                            failed: "失败",
                            unsupported: "不支持",
                            not_requested: "未设置",
                            not_set: "未设置",
                          }[account.password_status ?? ""] ??
                          account.password_status ??
                          "未记录"
                        }
                        title={account.security_error ?? undefined}
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={account.mfa_status}
                        label={
                          {
                            enabled: "已验证",
                            failed: "失败",
                            not_requested: "未启用",
                            not_enabled: "未启用",
                            skipped_partial: "已跳过",
                          }[account.mfa_status ?? ""] ??
                          account.mfa_status ??
                          "未记录"
                        }
                        title={account.security_error ?? undefined}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {formatDate(account.claimed_at)}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {formatDate(account.finished_at)}
                    </TableCell>
                    <TableCell>
                      <AccountActions account={account} />
                    </TableCell>
                  </TableRow>
                ))}
              {!accounts.isLoading &&
                !accounts.isError &&
                !accounts.data?.items.length && (
                  <TableRow>
                    <TableCell className="h-52 text-center" colSpan={9}>
                      <Inbox className="mx-auto mb-3 size-7 text-muted-foreground" />
                      <p className="text-sm font-medium">没有匹配的账号</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        调整筛选条件或导入新账号。
                      </p>
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
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </section>

      <ImportDialog />
      <DeleteAccountDialog />
    </div>
  )
}
