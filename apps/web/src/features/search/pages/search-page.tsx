import { Link, useSearchParams } from "react-router"
import { Inbox, Mail, Workflow } from "lucide-react"

import {
  getListAccountsApiAccountsGetQueryKey,
  getListPipelineRunsApiPipelinesRunsGetQueryKey,
  useListAccountsApiAccountsGet,
  useListPipelineRunsApiPipelinesRunsGet,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { pipelineStatus } from "@/features/pipelines/lib/pipeline-state"
import { formatCompactBeijingDateTime } from "@/lib/date-time"

export function SearchPage() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get("q")?.trim() ?? ""
  const accountParams = { search: query, limit: 20, offset: 0 }
  const pipelineParams = { search: query, limit: 20, offset: 0 }
  const accounts = useListAccountsApiAccountsGet(
    accountParams,
    {
      query: {
        queryKey: getListAccountsApiAccountsGetQueryKey(accountParams),
        enabled: Boolean(query),
      },
    }
  )
  const pipelines = useListPipelineRunsApiPipelinesRunsGet(
    pipelineParams,
    {
      query: {
        queryKey: getListPipelineRunsApiPipelinesRunsGetQueryKey(pipelineParams),
        enabled: Boolean(query),
      },
    }
  )
  const empty =
    !accounts.isLoading &&
    !pipelines.isLoading &&
    !accounts.data?.items.length &&
    !pipelines.data?.items.length

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <h1 className="text-xl font-semibold">搜索结果</h1>
      {query && (
        <p className="mt-1 text-sm text-muted-foreground">
          “{query}” · 账号 {accounts.data?.total ?? 0} · 轮次{" "}
          {pipelines.data?.total ?? 0}
        </p>
      )}

      <section className="mt-6 border-t" aria-label="匹配账号">
        <h2 className="flex items-center gap-2 py-3 text-sm font-medium">
          <Mail className="size-4" />
          邮箱账号
        </h2>
        <div className="divide-y border-y">
          {(accounts.data?.items ?? []).map((account) => (
            <Link
              className="flex items-center gap-3 px-3 py-3 hover:bg-muted/40"
              key={account.email}
              to={`/accounts?search=${encodeURIComponent(account.email)}`}
            >
              <span className="min-w-0 flex-1 truncate font-mono text-xs">
                {account.email}
              </span>
              <StatusBadge status={account.status} />
            </Link>
          ))}
        </div>
      </section>

      <section className="mt-6 border-t" aria-label="匹配轮次">
        <h2 className="flex items-center gap-2 py-3 text-sm font-medium">
          <Workflow className="size-4" />
          流水线轮次
        </h2>
        <div className="divide-y border-y">
          {(pipelines.data?.items ?? []).map((run) => (
            <Link
              className="flex items-center gap-3 px-3 py-3 hover:bg-muted/40"
              key={run.id}
              to={`/pipelines/${run.id}`}
            >
              <span className="min-w-0 flex-1 truncate font-mono text-xs">
                {run.id}
              </span>
              <StatusBadge {...pipelineStatus(run)} />
              <span className="font-mono text-xs text-muted-foreground">
                {formatCompactBeijingDateTime(run.created_at)}
              </span>
            </Link>
          ))}
        </div>
      </section>

      {empty && (
        <div className="py-20 text-center text-sm text-muted-foreground">
          <Inbox className="mx-auto mb-3 size-7" />
          没有匹配的账号或轮次
        </div>
      )}
    </div>
  )
}
