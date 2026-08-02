import { Link } from "react-router"
import { Ban, ChevronRight, Pause, Play, Trash2 } from "lucide-react"

import {
  BulkPipelineAction,
  PipelineRunKind,
  type PipelineRunSummary,
  PipelineStatus,
} from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"
import { CreateKakaoPipelineDialog } from "@/features/pipelines/components/create-kakao-dialog"
import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import { RowCheckbox } from "@/features/pipelines/components/pipeline-ui"
import {
  pipelineStatus,
  PIPELINE_KIND_LABELS,
} from "@/features/pipelines/lib/pipeline-state"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { Button } from "@workspace/ui/components/button"
import { TableCell, TableRow } from "@workspace/ui/components/table"

export function PipelineRunRow({
  run,
  selected,
  setSelected,
  pending,
  onAction,
  onDelete,
}: {
  run: PipelineRunSummary
  selected: string[]
  setSelected: (ids: string[]) => void
  pending: boolean
  onAction: (action: BulkPipelineAction, runId: string) => void
  onDelete: (runId: string) => void
}) {
  const active =
    run.status === PipelineStatus.queued ||
    run.status === PipelineStatus.running ||
    run.status === PipelineStatus.paused
  const removable =
    run.status === PipelineStatus.completed ||
    run.status === PipelineStatus.failed ||
    run.status === PipelineStatus.canceled

  return (
    <TableRow>
      <TableCell>
        <RowCheckbox
          id={run.id}
          selected={selected}
          setSelected={setSelected}
        />
      </TableCell>
      <TableCell className="font-mono text-xs">
        <Link className="hover:underline" to={`/pipelines/${run.id}`}>
          {run.id}
        </Link>
      </TableCell>
      <TableCell>
        <StatusBadge status={run.kind} label={PIPELINE_KIND_LABELS[run.kind]} />
      </TableCell>
      <TableCell>
        <StatusBadge {...pipelineStatus(run)} />
      </TableCell>
      <TableCell className="tabular-nums">{run.target_count}</TableCell>
      <TableCell className="tabular-nums">{run.registered_count}</TableCell>
      <TableCell className="tabular-nums">{run.kakao_task_count}</TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {formatCompactBeijingDateTime(run.started_at ?? run.created_at)}
      </TableCell>
      <TableCell className="text-right">
        {run.kind === PipelineRunKind.registration &&
          run.registered_count > 0 && (
            <>
              {!run.kakao_enabled && (
                <CreateKakaoPipelineDialog iconOnly sourceRunId={run.id} />
              )}
              <CreateSecurityPipelineDialog iconOnly sourceRunId={run.id} />
            </>
          )}
        {run.kind === PipelineRunKind.registration &&
          (run.status === PipelineStatus.queued ||
            run.status === PipelineStatus.running) && (
            <Button
              aria-label={`暂停轮次 ${run.id}`}
              disabled={pending}
              onClick={() => onAction(BulkPipelineAction.pause, run.id)}
              size="icon-sm"
              title="暂停"
              variant="ghost"
            >
              <Pause />
            </Button>
          )}
        {run.kind === PipelineRunKind.registration &&
          run.status === PipelineStatus.paused && (
            <Button
              aria-label={`恢复轮次 ${run.id}`}
              disabled={pending}
              onClick={() => onAction(BulkPipelineAction.resume, run.id)}
              size="icon-sm"
              title="恢复"
              variant="ghost"
            >
              <Play />
            </Button>
          )}
        {active && (
          <Button
            aria-label={`取消轮次 ${run.id}`}
            disabled={pending}
            onClick={() => onAction(BulkPipelineAction.cancel, run.id)}
            size="icon-sm"
            title="取消"
            variant="ghost"
          >
            <Ban />
          </Button>
        )}
        {removable && (
          <Button
            aria-label={`删除轮次 ${run.id}`}
            disabled={pending}
            onClick={() => onDelete(run.id)}
            size="icon-sm"
            title="删除"
            variant="ghost"
          >
            <Trash2 />
          </Button>
        )}
        <Button
          asChild
          aria-label={`查看轮次 ${run.id}`}
          size="icon-sm"
          variant="ghost"
        >
          <Link to={`/pipelines/${run.id}`}>
            <ChevronRight />
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  )
}
