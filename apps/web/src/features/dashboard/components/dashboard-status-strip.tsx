import { Activity, Boxes, CircleAlert, CircleCheck, Mail } from "lucide-react"

import type { DashboardResponse } from "@/api/generated"
import { StatusBadge } from "@/components/status-badge"

function operationalState(data: DashboardResponse) {
  const failures =
    data.accounts.failed + data.pipelines.failed + data.jobs.failed
  if (failures > 0) return { status: "failed", label: "存在异常" }
  if (data.pipelines.active > 0 || data.jobs.running > 0)
    return { status: "running", label: "正在运行" }
  if (data.jobs.queued > 0) return { status: "queued", label: "等待执行" }
  if (data.accounts.available > 0 || data.cards.active > 0)
    return { status: "completed", label: "资源就绪" }
  return { status: "unknown", label: "等待配置" }
}

export function DashboardStatusStrip({ data }: { data: DashboardResponse }) {
  const issues = data.accounts.failed + data.pipelines.failed + data.jobs.failed
  const state = operationalState(data)
  const metrics = [
    {
      label: "可用邮箱",
      value: data.accounts.available,
      detail: `${data.cards.active} 个启用卡密`,
      icon: Mail,
    },
    {
      label: "执行中",
      value: data.pipelines.active,
      detail: `${data.jobs.running} 运行 · ${data.jobs.queued} 排队`,
      icon: Activity,
    },
    {
      label: "注册结果",
      value: data.registration_results,
      detail: `${data.pipelines.completed} 个完成轮次`,
      icon: Boxes,
    },
    {
      label: "需要处理",
      value: issues,
      detail: `${data.jobs.failed} 个失败任务`,
      icon: issues > 0 ? CircleAlert : CircleCheck,
    },
  ]

  return (
    <section aria-label="运行概览" className="border-y">
      <div className="flex items-center justify-between gap-3 bg-muted/30 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs font-medium">
          <Activity className="size-3.5 text-muted-foreground" />
          当前运行态
        </div>
        <StatusBadge status={state.status} label={state.label} />
      </div>
      <div className="grid grid-cols-2 border-t lg:grid-cols-4">
        {metrics.map((metric, index) => (
          <div
            className={`min-w-0 px-4 py-4 sm:px-5 ${
              index % 2 ? "border-l" : ""
            } ${index >= 2 ? "border-t lg:border-t-0" : ""} ${
              index ? "lg:border-l" : ""
            }`}
            key={metric.label}
          >
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <metric.icon className="size-3.5" />
              {metric.label}
            </div>
            <div className="mt-2 flex items-end gap-2">
              <strong className="font-mono text-2xl font-semibold tabular-nums">
                {metric.value}
              </strong>
              <span className="mb-0.5 truncate text-xs text-muted-foreground">
                {metric.detail}
              </span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
