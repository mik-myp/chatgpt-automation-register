import { useDeferredValue, useState } from "react"
import { useNavigate } from "react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw, Search, ShieldCheck } from "lucide-react"
import { toast } from "sonner"

import {
  type PipelineRunSummary,
  type SecurityPipelineCandidateList,
  type SecurityPipelineCandidatePage,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { TablePagination } from "@/components/table-pagination"
import { ApiError, apiRequest } from "@/lib/api-client"
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

export function CreateSecurityPipelineDialog({
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
    SecurityPipelineCandidateList | SecurityPipelineCandidatePage,
    ApiError
  >({
    queryKey: sourceRunId
      ? ["/api/pipelines/runs", sourceRunId, "security-candidates"]
      : ["/api/pipelines/runs/security-candidates", candidateParams],
    queryFn: () =>
      sourceRunId
        ? apiRequest<SecurityPipelineCandidateList>(
            `/api/pipelines/runs/${encodeURIComponent(sourceRunId)}/security-candidates`
          )
        : apiRequest<SecurityPipelineCandidatePage>(
            "/api/pipelines/runs/security-candidates",
            { params: candidateParams }
          ),
    enabled: open,
  })
  const mutation = useMutation<
    PipelineRunSummary,
    ApiError,
    { emails: string[] }
  >({
    mutationFn: (data) =>
      apiRequest(
        sourceRunId
          ? `/api/pipelines/runs/${encodeURIComponent(sourceRunId)}/security-runs`
          : "/api/pipelines/runs/security-runs",
        { method: "POST", data }
      ),
    onSuccess: (run) => {
      setOpen(false)
      void queryClient.invalidateQueries({ queryKey: ["/api/pipelines/runs"] })
      toast.success(`已创建安全处理轮次 ${run.id.slice(0, 8)}`)
      void navigate(`/pipelines/${run.id}`)
    },
    onError: (error) => toast.error(error.message),
  })
  const rows = candidates.data?.items ?? []
  const pageEmails = rows.map((item) => item.email)
  const selected = selectedEmails ?? (sourceRunId ? pageEmails : [])
  const selectedOnPage = pageEmails.filter((email) =>
    selected.includes(email)
  ).length
  const allSelected = rows.length > 0 && selectedOnPage === rows.length
  const total =
    candidates.data && "total" in candidates.data
      ? candidates.data.total
      : rows.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
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
          aria-label={iconOnly ? "创建修改密码与 MFA 流水线" : undefined}
          size={iconOnly ? "icon-sm" : sourceRunId ? "sm" : "default"}
          title={iconOnly ? "修改密码与 MFA" : undefined}
          variant="outline"
        >
          <ShieldCheck />
          {!iconOnly && "修改密码与 MFA"}
        </Button>
      </DialogTrigger>
      <DialogContent className="flex h-[min(42rem,calc(100svh-2rem))] min-h-0 flex-col overflow-hidden sm:max-w-3xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>创建安全处理流水线</DialogTitle>
          <DialogDescription>
            {sourceRunId
              ? "选择该注册轮次中密码或 MFA 尚未全部完成的账号。"
              : "从邮箱账号中选择需要修改密码或启用 MFA 的账号。"}
          </DialogDescription>
        </DialogHeader>
        {!sourceRunId && (
          <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="搜索待处理邮箱"
                className="pl-8"
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(0)
                }}
                placeholder="搜索邮箱"
                value={search}
              />
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">
              待处理 {total} 个，已选 {selected.length} 个
            </span>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-auto border-y">
          <Table className="min-w-160">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    aria-label="选择全部待处理账号"
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
                <TableHead>密码</TableHead>
                <TableHead>MFA</TableHead>
                <TableHead>最近错误</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {candidates.isLoading &&
                Array.from({ length: 6 }, (_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={5}>
                      <div className="h-5 animate-pulse rounded bg-muted" />
                    </TableCell>
                  </TableRow>
                ))}
              {rows.map((item) => (
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
                      status={item.needs_password ? "not_set" : "set"}
                      label={item.needs_password ? "待设置" : "已设置"}
                    />
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      status={item.needs_mfa ? "not_enabled" : "enabled"}
                      label={item.needs_mfa ? "待启用" : "已启用"}
                    />
                  </TableCell>
                  <TableCell
                    className="max-w-60 truncate text-xs text-destructive"
                    title={item.security_error ?? undefined}
                  >
                    {item.security_error || "-"}
                  </TableCell>
                </TableRow>
              ))}
              {candidates.isError && (
                <TableRow>
                  <TableCell className="h-48 text-center" colSpan={5}>
                    <p className="text-sm font-medium text-destructive">
                      无法读取待处理账号
                    </p>
                    <Button
                      className="mt-3"
                      onClick={() => void candidates.refetch()}
                      size="sm"
                      variant="outline"
                    >
                      <RefreshCw />
                      重新加载
                    </Button>
                  </TableCell>
                </TableRow>
              )}
              {!candidates.isLoading &&
                !candidates.isError &&
                rows.length === 0 && (
                  <TableRow>
                    <TableCell className="h-48 text-center" colSpan={5}>
                      <ShieldCheck className="mx-auto mb-3 size-7 text-muted-foreground" />
                      <p className="text-sm font-medium">
                        {sourceRunId
                          ? "该轮次账号均已完成密码和 MFA"
                          : search
                            ? "没有匹配的待处理邮箱"
                            : "所有邮箱账号均已完成密码和 MFA"}
                      </p>
                    </TableCell>
                  </TableRow>
                )}
            </TableBody>
          </Table>
        </div>
        {!sourceRunId && pageCount > 1 && (
          <div className="shrink-0">
            <TablePagination
              page={page}
              pageCount={pageCount}
              onPageChange={setPage}
            />
          </div>
        )}
        <DialogFooter className="shrink-0">
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={!selected.length || mutation.isPending}
            onClick={() => mutation.mutate({ emails: selected })}
          >
            <ShieldCheck />
            {mutation.isPending
              ? "正在创建"
              : `创建安全流水线（${selected.length}）`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
