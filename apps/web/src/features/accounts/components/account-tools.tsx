import { type ReactNode, useState } from "react"
import { useNavigate } from "react-router"
import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import {
  Ellipsis,
  Play,
  RefreshCcw,
  RotateCcw,
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
  useBulkAccountActionApiAccountsBatchPost,
  useDeleteAccountApiAccountsEmailDelete,
  useImportAccountsApiAccountsImportPost,
  useMaintainAccountsApiAccountsMaintenancePost,
  useReleaseAccountApiAccountsEmailReleasePost,
  useResetAccountApiAccountsEmailResetPost,
} from "@/api/generated"
import { TextFileImportField } from "@/components/text-file-import-field"
import { ApiError } from "@/lib/api-client"
import { importEntryCount, normalizeImportText } from "@/lib/text-import"
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"

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

export function StatusBand({ stats }: { stats?: AccountStats }) {
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

export function CredentialTooltip({
  label,
  value,
  children,
}: {
  label: string
  value?: string | null
  children: ReactNode
}) {
  if (!value) return children
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help">{children}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-md" side="top" sideOffset={6}>
        <div className="grid min-w-0 gap-1">
          <span className="text-[11px] opacity-70">{label}</span>
          <span className="font-mono break-all select-all">{value}</span>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

export function AccountActions({ account }: { account: AccountSummary }) {
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

export function AccountMaintenanceActions({
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

export function ImportDialog() {
  const queryClient = useQueryClient()
  const [text, setText] = useState("")
  const open = useAccountsStore((state) => state.importOpen)
  const setOpen = useAccountsStore((state) => state.setImportOpen)
  const entryCount = importEntryCount(text)
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
            选择文件或直接粘贴，重复邮箱保留当前状态。
          </DialogDescription>
        </DialogHeader>
        <TextFileImportField
          fileLabel="选择邮箱导入文件"
          onValueChange={setText}
          placeholder="直接粘贴邮箱内容"
          textareaLabel="邮箱内容"
          value={text}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={!entryCount || mutation.isPending}
            onClick={() =>
              mutation.mutate({ data: { text: normalizeImportText(text) } })
            }
          >
            <Upload />
            {mutation.isPending ? "正在导入" : `导入邮箱（${entryCount}）`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DeleteAccountDialog() {
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

export function BulkAccountActions() {
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
        }
        const label =
          labels[variables.data.action as keyof typeof labels] ?? "账号操作"
        const skipped = result.skipped ? `，跳过 ${result.skipped}` : ""
        toast.success(
          result.job_id
            ? `${label}已加入后台队列：${result.processed} 个${skipped}`
            : `${label}完成：处理 ${result.processed}${skipped}`
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
