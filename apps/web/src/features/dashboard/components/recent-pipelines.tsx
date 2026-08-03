import { ArrowRight, Workflow } from "lucide-react"
import { Link } from "react-router"

import { PipelineRunKind, type PipelineRunSummary } from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import {
  pipelineStatus,
  PIPELINE_KIND_LABELS,
} from "@/features/pipelines/lib/pipeline-state"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { Button } from "@workspace/ui/components/button"
import { Skeleton } from "@workspace/ui/components/skeleton"

function runProgress(run: PipelineRunSummary) {
  const successful =
    run.kind === PipelineRunKind.kakao
      ? run.kakao_task_count
      : run.registered_count
  const processed = Math.min(run.target_count, successful + run.failed_count)
  const percent = run.target_count
    ? Math.round((processed / run.target_count) * 100)
    : 0
  return { processed, percent }
}

function RecentPipelineRow({ run }: { run: PipelineRunSummary }) {
  const progress = runProgress(run)
  const status = pipelineStatus(run)
  return (
    <Link
      className="group grid min-w-0 gap-3 border-t px-1 py-3.5 transition-colors hover:bg-muted/30 sm:grid-cols-[minmax(0,1fr)_8rem_7rem] sm:items-center sm:px-3"
      to={`/pipelines/${run.id}`}
    >
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <StatusBadge
            status={run.kind}
            label={PIPELINE_KIND_LABELS[run.kind]}
          />
          <span className="truncate font-mono text-xs font-medium">
            {run.id.slice(0, 8)}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <div
            aria-label={`轮次进度 ${progress.percent}%`}
            className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={progress.percent}
          >
            <div
              className="h-full rounded-full bg-foreground/70 transition-[width]"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
            {progress.processed}/{run.target_count}
          </span>
        </div>
      </div>
      <div className="flex items-center sm:justify-center">
        <StatusBadge {...status} />
      </div>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground sm:justify-end">
        <span className="font-mono">
          {formatCompactBeijingDateTime(run.started_at ?? run.created_at)}
        </span>
        <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}

export function RecentPipelines({
  runs,
  loading,
  error,
}: {
  runs: PipelineRunSummary[]
  loading: boolean
  error: boolean
}) {
  return (
    <section aria-labelledby="recent-pipelines-title" className="min-w-0">
      <div className="flex items-center justify-between gap-3 pb-3">
        <div>
          <h2 className="text-sm font-semibold" id="recent-pipelines-title">
            最近流水线
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            最新创建的 6 个轮次
          </p>
        </div>
        <Button asChild size="sm" variant="ghost">
          <Link to="/pipelines">
            查看全部
            <ArrowRight />
          </Link>
        </Button>
      </div>
      <div className="border-y">
        {loading &&
          Array.from({ length: 3 }, (_, index) => (
            <div
              className="grid h-18 items-center gap-3 border-t px-3 first:border-t-0 sm:grid-cols-[minmax(0,1fr)_8rem_7rem]"
              key={index}
            >
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-5 w-16 sm:justify-self-center" />
              <Skeleton className="h-4 w-24 sm:justify-self-end" />
            </div>
          ))}
        {!loading && error && (
          <div className="flex min-h-48 items-center justify-center px-4 text-sm text-destructive">
            最近流水线加载失败
          </div>
        )}
        {!loading && !error && runs.length === 0 && (
          <div className="flex min-h-52 flex-col items-center justify-center px-4 text-center">
            <div className="flex size-9 items-center justify-center rounded-md border bg-muted/30">
              <Workflow className="size-4 text-muted-foreground" />
            </div>
            <p className="mt-3 text-sm font-medium">暂无流水线轮次</p>
          </div>
        )}
        {!loading &&
          !error &&
          runs.map((run) => <RecentPipelineRow key={run.id} run={run} />)}
      </div>
    </section>
  )
}
