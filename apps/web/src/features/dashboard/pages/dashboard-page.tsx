import { Link } from "react-router"
import { ArrowRight } from "lucide-react"

import { useGetDashboardApiDashboardGet } from "@/api/generated"

type Metric = {
  label: string
  value: number
}

function MetricGroup({
  title,
  href,
  metrics,
}: {
  title: string
  href: string
  metrics: Metric[]
}) {
  return (
    <section className="border-t" aria-label={title}>
      <div className="flex items-center justify-between py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        <Link
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          to={href}
        >
          查看
          <ArrowRight className="size-3.5" />
        </Link>
      </div>
      <div className="grid grid-cols-2 border-y bg-muted/20 sm:grid-cols-4">
        {metrics.map((metric, index) => (
          <div
            className={`px-4 py-5 ${index ? "border-l" : ""}`}
            key={metric.label}
          >
            <div className="text-xs text-muted-foreground">{metric.label}</div>
            <div className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {metric.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export function DashboardPage() {
  const dashboard = useGetDashboardApiDashboardGet()
  const data = dashboard.data

  return (
    <div className="h-full min-h-0 overflow-auto">
      <div className="flex min-h-full flex-col gap-6">
        <h1 className="text-xl font-semibold">工作台</h1>

        <MetricGroup
          href="/accounts"
          title="邮箱号池"
          metrics={[
            { label: "账号总数", value: data?.accounts.total ?? 0 },
            { label: "可用", value: data?.accounts.available ?? 0 },
            { label: "使用中", value: data?.accounts.in_use ?? 0 },
            {
              label: "完成 / 失败",
              value: (data?.accounts.done ?? 0) + (data?.accounts.failed ?? 0),
            },
          ]}
        />

        <MetricGroup
          href="/cards"
          title="卡密库存"
          metrics={[
            { label: "卡密总数", value: data?.cards.total ?? 0 },
            { label: "已启用", value: data?.cards.active ?? 0 },
            { label: "已停用", value: data?.cards.inactive ?? 0 },
          ]}
        />

        <MetricGroup
          href="/pipelines"
          title="流水线与任务"
          metrics={[
            { label: "轮次总数", value: data?.pipelines.total ?? 0 },
            { label: "活动轮次", value: data?.pipelines.active ?? 0 },
            { label: "排队任务", value: data?.jobs.queued ?? 0 },
            { label: "运行任务", value: data?.jobs.running ?? 0 },
          ]}
        />

        <MetricGroup
          href="/results"
          title="注册结果"
          metrics={[
            { label: "结果总数", value: data?.registration_results ?? 0 },
            { label: "已完成轮次", value: data?.pipelines.completed ?? 0 },
            { label: "失败轮次", value: data?.pipelines.failed ?? 0 },
            { label: "失败任务", value: data?.jobs.failed ?? 0 },
          ]}
        />
      </div>
    </div>
  )
}
