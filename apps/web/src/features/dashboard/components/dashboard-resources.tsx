import {
  ArrowRight,
  BriefcaseBusiness,
  KeyRound,
  Mail,
  Workflow,
} from "lucide-react"
import { Link } from "react-router"

import type { DashboardResponse } from "@/api/generated"

function StockRow({
  href,
  icon: Icon,
  label,
  available,
  total,
  detail,
}: {
  href: string
  icon: typeof Mail
  label: string
  available: number
  total: number
  detail: string
}) {
  const percent = total ? Math.round((available / total) * 100) : 0
  return (
    <Link className="group block border-t py-4 first:border-t-0" to={href}>
      <div className="flex items-start gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted/30">
          <Icon className="size-4 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium">{label}</span>
            <span className="font-mono text-sm font-semibold tabular-nums">
              {available}
              <span className="font-normal text-muted-foreground">
                /{total}
              </span>
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-emerald-600 transition-[width] dark:bg-emerald-400"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{detail}</span>
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
          </div>
        </div>
      </div>
    </Link>
  )
}

export function DashboardResources({ data }: { data: DashboardResponse }) {
  return (
    <aside className="min-w-0 space-y-7" aria-label="资源与运行明细">
      <section aria-labelledby="resource-stock-title">
        <div className="pb-3">
          <h2 className="text-sm font-semibold" id="resource-stock-title">
            资源库存
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">当前可调度数量</p>
        </div>
        <div className="border-y">
          <StockRow
            available={data.accounts.available}
            detail={`使用中 ${data.accounts.in_use} · 完成 ${data.accounts.done} · 失败 ${data.accounts.failed}`}
            href="/accounts"
            icon={Mail}
            label="邮箱"
            total={data.accounts.total}
          />
          <StockRow
            available={data.cards.active}
            detail={`停用 ${data.cards.inactive}`}
            href="/cards"
            icon={KeyRound}
            label="卡密"
            total={data.cards.total}
          />
        </div>
      </section>

      <section aria-labelledby="runtime-detail-title">
        <div className="pb-3">
          <h2 className="text-sm font-semibold" id="runtime-detail-title">
            运行明细
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            流水线与后台任务状态
          </p>
        </div>
        <div className="border-y">
          <Link className="group flex items-start gap-3 py-4" to="/pipelines">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted/30">
              <Workflow className="size-4 text-muted-foreground" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium">流水线</span>
                <span className="font-mono text-sm font-semibold tabular-nums">
                  {data.pipelines.total}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                <span>活动 {data.pipelines.active}</span>
                <span>完成 {data.pipelines.completed}</span>
                <span className="text-right">失败 {data.pipelines.failed}</span>
              </div>
              <div className="mt-2 flex items-center justify-end">
                <ArrowRight className="size-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </div>
            </div>
          </Link>
          <div className="flex items-start gap-3 border-t py-4">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-muted/30">
              <BriefcaseBusiness className="size-4 text-muted-foreground" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium">后台任务</span>
                <span className="font-mono text-sm font-semibold tabular-nums">
                  {data.jobs.queued + data.jobs.running + data.jobs.failed}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                <span>排队 {data.jobs.queued}</span>
                <span>运行 {data.jobs.running}</span>
                <span className="text-right">失败 {data.jobs.failed}</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </aside>
  )
}
