import { useState } from "react"
import { Check, Clipboard, Eye, EyeOff } from "lucide-react"
import { toast } from "sonner"
import { QRCodeSVG } from "qrcode.react"

import { StatusBadge } from "@/components/status-badge"
import { formatBeijingDateTime } from "@/lib/date-time"
import { Button } from "@workspace/ui/components/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@workspace/ui/components/tooltip"

export function TokenState({ value }: { value: boolean }) {
  return value ? (
    <Check className="size-4 text-emerald-600" />
  ) : (
    <span className="text-muted-foreground">-</span>
  )
}

export function SecurityState({
  kind,
  status,
  value,
}: {
  kind: "password" | "mfa"
  status?: string | null
  value?: string | null
}) {
  const labels: Record<string, string> = {
    set: "已设置",
    available: "可用",
    enabled: "已启用",
    failed: "失败",
    unsupported: "不支持",
    not_requested: "未开启",
    skipped_partial: "已跳过",
  }
  const effectiveStatus =
    status ?? (value ? (kind === "mfa" ? "enabled" : "set") : null)
  if (!effectiveStatus)
    return <span className="text-xs text-muted-foreground">未记录</span>
  const badge = (
    <StatusBadge
      status={effectiveStatus}
      label={
        labels[effectiveStatus] ??
        `${kind === "mfa" ? "MFA" : "密码"}: ${effectiveStatus}`
      }
    />
  )
  if (!value) return badge
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help">{badge}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-md" side="top" sideOffset={6}>
        <div className="grid gap-1">
          <span className="text-[11px] opacity-70">
            {kind === "mfa" ? "Authenticator 密钥" : "ChatGPT 密码"}
          </span>
          <span className="font-mono break-all select-all">{value}</span>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

export function SecurityDetails({
  metadata,
}: {
  metadata: Record<string, unknown>
}) {
  const security = metadata.account_security
  if (!security || typeof security !== "object") return null
  const outcomes = security as Record<string, unknown>
  const rows = [
    ["密码", outcomes.password],
    ["Authenticator MFA", outcomes.mfa],
  ] as const
  return (
    <div className="border-b py-3">
      <div className="mb-2 text-xs font-medium">账号安全状态</div>
      <div className="grid gap-2">
        {rows.map(([label, raw]) => {
          const outcome =
            raw && typeof raw === "object"
              ? (raw as Record<string, unknown>)
              : {}
          return (
            <div className="grid gap-0.5 text-xs" key={label}>
              <div className="flex items-center gap-2">
                <span className="w-36 text-muted-foreground">{label}</span>
                <span>{String(outcome.status ?? "未记录")}</span>
              </div>
              {outcome.error ? (
                <p className="pl-4 leading-5 text-destructive">
                  {String(outcome.error)}
                </p>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function PlusState({
  state,
  label,
  error,
  checkedAt,
  planType,
  subscriptionPlan,
  activeSubscription,
  expiresAt,
}: {
  state?: string | null
  label?: string | null
  error?: string | null
  checkedAt?: string | null
  planType?: string | null
  subscriptionPlan?: string | null
  activeSubscription?: boolean | null
  expiresAt?: string | null
}) {
  if (!state) {
    return <span className="text-xs text-muted-foreground">未检查</span>
  }
  const badge = <StatusBadge status={state} label={label || state} />
  const detail = [
    planType ? `套餐类型：${planType}` : "",
    subscriptionPlan ? `订阅计划：${subscriptionPlan}` : "",
    activeSubscription != null
      ? `有效订阅：${activeSubscription ? "是" : "否"}`
      : "",
    expiresAt ? `到期时间：${expiresAt}` : "",
    error,
    checkedAt ? `检查时间：${formatBeijingDateTime(checkedAt)}` : "",
  ].filter(Boolean)
  if (!detail.length) return badge
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help">{badge}</span>
      </TooltipTrigger>
      <TooltipContent className="max-w-md whitespace-pre-wrap" side="top">
        {detail.join("\n")}
      </TooltipContent>
    </Tooltip>
  )
}

export function CredentialField({
  label,
  value,
  sensitive = false,
}: {
  label: string
  value?: string | null
  sensitive?: boolean
}) {
  const [revealed, setRevealed] = useState(false)
  const displayValue =
    sensitive && value && !revealed ? "••••••••••••••••" : value
  return (
    <div className="grid gap-1.5 border-b py-3 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium">{label}</span>
        <div className="flex items-center gap-1">
          {sensitive && value && (
            <Button
              aria-label={revealed ? `隐藏${label}` : `显示${label}`}
              onClick={() => setRevealed((value) => !value)}
              size="icon-sm"
              variant="ghost"
            >
              {revealed ? <EyeOff /> : <Eye />}
            </Button>
          )}
          <Button
            aria-label={`复制${label}`}
            disabled={!value}
            onClick={() => {
              void navigator.clipboard.writeText(value ?? "")
              toast.success(`已复制${label}`)
            }}
            size="icon-sm"
            variant="ghost"
          >
            <Clipboard />
          </Button>
        </div>
      </div>
      <pre className="max-h-28 overflow-auto rounded-sm bg-muted/40 p-2 font-mono text-xs break-all whitespace-pre-wrap">
        {displayValue || "-"}
      </pre>
    </div>
  )
}

export function TotpSetup({
  email,
  secret,
}: {
  email: string
  secret?: string | null
}) {
  if (!secret) return null
  const uri = `otpauth://totp/${encodeURIComponent(`ChatGPT:${email}`)}?${new URLSearchParams(
    {
      secret,
      issuer: "ChatGPT",
      algorithm: "SHA1",
      digits: "6",
      period: "30",
    }
  )}`
  return (
    <div className="grid gap-4 border-b py-4 sm:grid-cols-[160px_1fr] sm:items-center">
      <div className="w-fit bg-white p-3">
        <QRCodeSVG size={136} value={uri} />
      </div>
      <div>
        <div className="text-xs font-medium">Authenticator App</div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          使用 Authenticator App 扫描二维码，或在应用中手动输入下方密钥。
        </p>
      </div>
    </div>
  )
}
