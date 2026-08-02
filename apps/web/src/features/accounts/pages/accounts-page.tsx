import { useDeferredValue } from "react"
import { Inbox, RefreshCcw, Search, Upload } from "lucide-react"

import {
  AccountStatus,
  getListAccountsApiAccountsGetQueryKey,
  useGetAccountStatsApiAccountsStatsGet,
  useListAccountsApiAccountsGet,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import {
  AccountActions,
  AccountMaintenanceActions,
  BulkAccountActions,
  CredentialTooltip,
  DeleteAccountDialog,
  ImportDialog,
  StatusBand,
} from "@/features/accounts/components/account-tools"
import {
  accountErrorMessage,
  ACCOUNT_STATUS_LABELS,
} from "@/features/accounts/lib/account-state"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { useAccountsStore } from "@/stores/accounts-store"
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
            <BulkAccountActions />
            <AccountMaintenanceActions total={total} status={status} />
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
                      {accountErrorMessage(accounts.error)}
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
                        label={ACCOUNT_STATUS_LABELS[account.status]}
                      />
                    </TableCell>
                    <TableCell>
                      <CredentialTooltip
                        label="ChatGPT 密码"
                        value={account.chatgpt_password}
                      >
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
                      </CredentialTooltip>
                    </TableCell>
                    <TableCell>
                      <CredentialTooltip
                        label="Authenticator 密钥"
                        value={account.totp_secret}
                      >
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
                      </CredentialTooltip>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {formatCompactBeijingDateTime(account.claimed_at)}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {formatCompactBeijingDateTime(account.finished_at)}
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
          total={total}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </section>

      <ImportDialog />
      <DeleteAccountDialog />
    </div>
  )
}
