import {
  type PipelineRunKind,
  type PipelineRunSummary,
  type PipelineStatus as PipelineStatusType,
} from "@/api/generated"

export const PIPELINE_KIND_LABELS: Record<PipelineRunKind, string> = {
  registration: "注册",
  account_security: "安全处理",
  kakao: "Kakao",
}

export const RUN_STATUS_LABELS: Record<PipelineStatusType, string> = {
  queued: "排队中",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  canceled: "已取消",
}

export function pipelineStatus(run: PipelineRunSummary) {
  if (run.status === "completed" && run.failed_count > 0) {
    return run.registered_count > 0
      ? { status: "partial", label: "部分成功" }
      : { status: "failed", label: "失败" }
  }
  return { status: run.status, label: RUN_STATUS_LABELS[run.status] }
}

export const TASK_STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  extracting: "提取中",
  done: "完成",
  failed: "失败",
  canceled: "已取消",
  scheduled: "待执行",
  registering: "注册中",
  registered: "已注册",
  submitting: "提交中",
  completed: "完成",
  skipped: "跳过",
}

export type StrictPlusCheckResponse = {
  items: Array<{
    email: string
    state: string
    label: string
    is_plus: boolean | null
    error: string
  }>
}
