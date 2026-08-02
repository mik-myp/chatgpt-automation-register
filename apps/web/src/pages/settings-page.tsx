import { type ReactNode, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import {
  ChevronLeft,
  ChevronRight,
  Database,
  Dices,
  Download,
  Eye,
  EyeOff,
  PlugZap,
  RefreshCw,
  Save,
  Trash2,
  Upload,
} from "lucide-react"
import { toast } from "sonner"

import {
  type BackupBundle,
  type BackupPreviewResponse,
  type DeliveryCopyRowFieldsItem,
  type DeliveryCopySettings,
  type SystemSettingsResponse,
  type SystemSettingsUpdate,
  useGetSettingsApiSettingsGet,
  useUpdateSettingsApiSettingsPut,
} from "@/api/generated"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import { Input } from "@workspace/ui/components/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import { Switch } from "@workspace/ui/components/switch"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"
import { Textarea } from "@workspace/ui/components/textarea"

type SmsCountryResponse = {
  items: Array<{
    id: string
    name: string
    safe: boolean
    price: number | null
    count: number | null
  }>
  live: boolean
}

function editableSettings(
  settings: SystemSettingsResponse | undefined
): SystemSettingsUpdate | null {
  if (!settings) return null
  return {
    registration: { ...settings.registration },
    mail: {
      source: settings.mail.source,
      cf_api_url: settings.mail.cf_api_url,
      cf_domain: settings.mail.cf_domain,
      cf_admin_token: "",
    },
    kakao: { ...settings.kakao },
    sms: {
      enabled: settings.sms.enabled,
      provider: settings.sms.provider,
      country: settings.sms.country,
      service: settings.sms.service,
      max_price: settings.sms.max_price,
      reuse_phone: settings.sms.reuse_phone,
      phone_success_max: settings.sms.phone_success_max,
      auto_country: settings.sms.auto_country,
      strict_whitelist: settings.sms.strict_whitelist,
      allowed_countries: settings.sms.allowed_countries,
      auto_min_stock: settings.sms.auto_min_stock,
      auto_max_price: settings.sms.auto_max_price,
      max_phone_attempts: settings.sms.max_phone_attempts,
      per_phone_timeout: settings.sms.per_phone_timeout,
      api_key: "",
    },
    export: {
      cpa: {
        enabled: settings.export.cpa?.enabled,
        url: settings.export.cpa?.url,
        timeout: settings.export.cpa?.timeout,
        key: "",
      },
      sub2api: {
        enabled: settings.export.sub2api?.enabled,
        url: settings.export.sub2api?.url,
        timeout: settings.export.sub2api?.timeout,
        key: "",
      },
      sub2api_group_ids: settings.export.sub2api_group_ids,
    },
    delivery_copy: {
      ...settings.delivery_copy,
      rows: (settings.delivery_copy.rows ?? []).map((row) => ({
        ...row,
        fields: [...row.fields],
      })),
    },
  }
}

const DELIVERY_FIELDS: Array<{
  value: DeliveryCopyRowFieldsItem
  label: string
  sample: string
}> = [
  {
    value: "payment_url",
    label: "支付链接",
    sample: "https://pay.example.com/checkout",
  },
  { value: "email", label: "邮箱", sample: "user@example.com" },
  {
    value: "mail_url",
    label: "邮件查询地址",
    sample: "https://mail.example.com/inbox",
  },
  { value: "chatgpt_password", label: "ChatGPT 密码", sample: "Password123" },
  {
    value: "totp_secret",
    label: "Authenticator 密钥",
    sample: "JBSWY3DPEHPK3PXP",
  },
]

function deliveryPreview(settings: DeliveryCopySettings) {
  const samples = Object.fromEntries(
    DELIVERY_FIELDS.map((field) => [field.value, field.sample])
  )
  const lines = (settings.rows ?? []).map((row) =>
    row.fields
      .map((field) => {
        const value = samples[field]
        const label = DELIVERY_FIELDS.find(
          (item) => item.value === field
        )?.label
        return settings.show_labels ? `${label}: ${value}` : value
      })
      .join(row.separator ?? " --- ")
  )
  const prefix = {
    none: "",
    number: "1.",
    chinese_number: "第1个",
    chinese: "第一个",
  }[settings.sequence_style ?? "chinese"]
  return [prefix, ...lines].filter(Boolean).join("\n")
}

function Field({
  label,
  className = "",
  children,
}: {
  label: string
  className?: string
  children: ReactNode
}) {
  return (
    <label
      className={`grid gap-1.5 text-xs text-muted-foreground ${className}`}
    >
      <span>{label}</span>
      {children}
    </label>
  )
}

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="border-t py-5 first:border-t-0 first:pt-0 last:border-b">
      <h2 className="mb-4 text-sm font-semibold">{title}</h2>
      {description && (
        <p className="-mt-2 mb-4 max-w-3xl text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      )}
      {children}
    </section>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex min-h-11 items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0">
      <span>{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  )
}

const BACKUP_SECTIONS = [
  ["settings", "系统配置"],
  ["accounts", "邮箱号池"],
  ["credentials", "注册凭据"],
  ["card_batches", "卡密批次"],
  ["cards", "卡密"],
] as const

function DataTransferPanel() {
  const [bundle, setBundle] = useState<BackupBundle | null>(null)
  const [sections, setSections] = useState<string[]>(
    BACKUP_SECTIONS.map(([value]) => value)
  )
  const [mode, setMode] = useState<"merge" | "overwrite">("merge")
  const [preview, setPreview] = useState<BackupPreviewResponse | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const exporting = useMutation<BackupBundle, ApiError>({
    mutationFn: () => apiRequest<BackupBundle>("/api/settings/data/export"),
    onSuccess: (value) => {
      const blob = new Blob([JSON.stringify(value, null, 2)], {
        type: "application/json",
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `gpt-auto-register-${new Date().toISOString().slice(0, 10)}.json`
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success("数据备份已导出")
    },
    onError: (error) => toast.error(error.message),
  })
  const previewing = useMutation<BackupPreviewResponse, ApiError>({
    mutationFn: () =>
      apiRequest<BackupPreviewResponse>("/api/settings/data/preview", {
        method: "POST",
        data: { bundle, sections, mode },
      }),
    onSuccess: (value) => {
      setPreview(value)
      setConfirmed(false)
    },
    onError: (error) => toast.error(error.message),
  })
  const importing = useMutation<
    { added: number; updated: number; unchanged: number; removed: number },
    ApiError
  >({
    mutationFn: () =>
      apiRequest("/api/settings/data/import", {
        method: "POST",
        data: {
          bundle,
          sections,
          mode,
          conflict_policy: "incoming",
        },
      }),
    onSuccess: (value) => {
      toast.success(
        `导入完成：新增 ${value.added}，更新 ${value.updated}，移除 ${value.removed}`
      )
      setBundle(null)
      setPreview(null)
      setConfirmed(false)
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Section
        title="导出备份"
        description="导出系统配置、邮箱凭据、注册令牌和 Authenticator 密钥。备份文件包含敏感数据，请只保存在可信设备。"
      >
        <div className="flex justify-end">
          <Button
            disabled={exporting.isPending}
            onClick={() => exporting.mutate()}
            variant="outline"
          >
            <Download />
            {exporting.isPending ? "正在导出" : "下载完整备份"}
          </Button>
        </div>
      </Section>
      <Section
        title="导入与同步"
        description="合并会保留本机额外数据；覆盖会移除所选分区中备份不存在的数据，但使用中的账号和被历史任务引用的卡密会受到保护。"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="备份文件">
            <Input
              accept="application/json,.json"
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (!file) return
                void file
                  .text()
                  .then((text) => {
                    const value = JSON.parse(text) as BackupBundle
                    if (
                      value.format !== "gpt-auto-register-backup" ||
                      value.version !== 1
                    )
                      throw new Error("不是受支持的数据备份")
                    setBundle(value)
                    setPreview(null)
                  })
                  .catch((error: unknown) =>
                    toast.error(
                      error instanceof Error
                        ? error.message
                        : "无法读取备份文件"
                    )
                  )
              }}
            />
          </Field>
          <Field label="导入模式">
            <Select
              value={mode}
              onValueChange={(value) => {
                setMode(value as "merge" | "overwrite")
                setPreview(null)
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="merge">合并</SelectItem>
                <SelectItem value="overwrite">覆盖所选分区</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {BACKUP_SECTIONS.map(([value, label]) => (
            <label className="flex items-center gap-2 text-sm" key={value}>
              <Checkbox
                checked={sections.includes(value)}
                onCheckedChange={(checked) => {
                  setSections((current) =>
                    checked
                      ? [...current, value]
                      : current.filter((item) => item !== value)
                  )
                  setPreview(null)
                }}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            disabled={!bundle || !sections.length || previewing.isPending}
            onClick={() => previewing.mutate()}
            variant="outline"
          >
            <Database />
            {previewing.isPending ? "正在分析" : "预览导入"}
          </Button>
        </div>
        {preview && (
          <div className="mt-5 border-t pt-4">
            <div className="overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="py-2">分区</th>
                    <th>新增</th>
                    <th>更新</th>
                    <th>不变</th>
                    <th>移除</th>
                    <th>保护</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(preview.sections).map(([name, value]) => (
                    <tr className="border-t" key={name}>
                      <td className="py-2">
                        {BACKUP_SECTIONS.find(([key]) => key === name)?.[1] ??
                          name}
                      </td>
                      <td>{value.added}</td>
                      <td>{value.updated}</td>
                      <td>{value.unchanged}</td>
                      <td>{value.removable}</td>
                      <td>{value.protected}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm">
              <Checkbox
                checked={confirmed}
                onCheckedChange={(value) => setConfirmed(value === true)}
              />
              我已确认以上变更并了解备份包含敏感凭据
            </label>
            <div className="mt-4 flex justify-end">
              <Button
                disabled={!confirmed || importing.isPending}
                onClick={() => importing.mutate()}
              >
                <Upload />
                {importing.isPending ? "正在导入" : "确认导入"}
              </Button>
            </div>
          </div>
        )}
      </Section>
    </div>
  )
}

export function SettingsPage() {
  const settings = useGetSettingsApiSettingsGet()
  const [draft, setForm] = useState<SystemSettingsUpdate | null>(null)
  const [showFixedPassword, setShowFixedPassword] = useState(false)
  const form = draft ?? editableSettings(settings.data)

  const mutation = useUpdateSettingsApiSettingsPut<ApiError>({
    mutation: {
      onSuccess: () => {
        toast.success("系统配置已保存")
        setForm((current) =>
          current
            ? {
                ...current,
                mail: { ...current.mail, cf_admin_token: "" },
                sms: { ...current.sms, api_key: "" },
                export: {
                  ...current.export,
                  cpa: { ...current.export.cpa, key: "" },
                  sub2api: { ...current.export.sub2api, key: "" },
                },
              }
            : current
        )
        void settings.refetch()
      },
      onError: (error) => toast.error(error.message),
    },
  })
  const smsTest = useMutation<{ balance: number }, ApiError>({
    mutationFn: () =>
      apiRequest<{ balance: number }>("/api/settings/sms/test", {
        method: "POST",
      }),
    onSuccess: (result) =>
      toast.success(`SMS 连接成功，余额 ${result.balance}`),
    onError: (error) => toast.error(error.message),
  })
  const smsCountries = useMutation<SmsCountryResponse, ApiError>({
    mutationFn: () =>
      apiRequest<SmsCountryResponse>("/api/settings/sms/countries"),
    onError: (error) => toast.error(error.message),
  })
  const mailTest = useMutation<{ message: string }, ApiError>({
    mutationFn: () =>
      apiRequest<{ message: string }>("/api/settings/mail/test", {
        method: "POST",
      }),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  })
  const exportTest = useMutation<
    { message: string },
    ApiError,
    "cpa" | "sub2api"
  >({
    mutationFn: (target) =>
      apiRequest<{ message: string }>(`/api/settings/export/${target}/test`, {
        method: "POST",
      }),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  })
  const kakaoTest = useMutation<{ message: string }, ApiError>({
    mutationFn: () =>
      apiRequest<{ message: string }>("/api/settings/kakao/test", {
        method: "POST",
      }),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  })

  if (!form)
    return <div className="text-sm text-muted-foreground">正在读取配置...</div>

  return (
    <div className="flex h-full min-h-0 flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">系统配置</h1>
        <Button
          disabled={mutation.isPending}
          onClick={() => mutation.mutate({ data: form })}
        >
          <Save />
          {mutation.isPending ? "正在保存" : "保存配置"}
        </Button>
      </div>

      <Tabs
        className="flex min-h-0 flex-1 flex-col"
        defaultValue="registration"
      >
        <TabsList className="w-full shrink-0 justify-start overflow-x-auto">
          <TabsTrigger className="shrink-0" value="registration">
            注册
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="mail">
            邮箱
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="kakao">
            Kakao
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="sms">
            接码
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="export">
            自动导出
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="delivery">
            交付复制
          </TabsTrigger>
          <TabsTrigger className="shrink-0" value="data">
            数据同步
          </TabsTrigger>
        </TabsList>

        <TabsContent
          className="mt-5 min-h-0 flex-1 overflow-auto"
          value="registration"
        >
          <div className="mx-auto w-full max-w-5xl">
            <Section
              title="运行参数"
              description="这里是批量流水线的默认值；新建轮次未填写覆盖值时自动继承。并发过高会同时增加代理、邮箱和接码服务压力。"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="默认并发数">
                  <Input
                    max={50}
                    min={1}
                    type="number"
                    value={form.registration.concurrency ?? 10}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        registration: {
                          ...form.registration,
                          concurrency: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
                <Field label="OTP 超时（秒）">
                  <Input
                    max={300}
                    min={1}
                    type="number"
                    value={form.registration.otp_timeout ?? 10}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        registration: {
                          ...form.registration,
                          otp_timeout: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
              </div>
            </Section>

            <Section
              title="网络"
              description="固定代理优先于代理池；未设置固定代理时，每个注册项从代理池随机选择一条。支持 http、https 和 socks5 地址。"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field className="sm:col-span-2" label="固定代理">
                  <Input
                    placeholder="http://user:password@host:port"
                    value={form.registration.proxy ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        registration: {
                          ...form.registration,
                          proxy: event.target.value,
                        },
                      })
                    }
                  />
                </Field>
                <Field className="sm:col-span-2" label="代理池（每行一个）">
                  <Textarea
                    className="min-h-32 resize-y font-mono text-xs"
                    value={form.registration.proxy_pool ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        registration: {
                          ...form.registration,
                          proxy_pool: event.target.value,
                        },
                      })
                    }
                  />
                </Field>
              </div>
            </Section>

            <Section
              title="账号策略"
              description="开启后，邮箱被识别为已有 OpenAI 账号时继续走登录取凭证；关闭后该账号会快速失败。Access、Session 和 Refresh Token 始终保存。"
            >
              <Toggle
                label="允许已有账号登录"
                checked={form.registration.allow_existing_login ?? true}
                onChange={(checked) =>
                  setForm({
                    ...form,
                    registration: {
                      ...form.registration,
                      allow_existing_login: checked,
                    },
                  })
                }
              />
            </Section>

            <Section
              title="账号安全"
              description="可选择不设置密码、为每个账号生成独立密码，或让所有新账号使用同一个固定密码。MFA 会在注册完成后通过新的邮箱验证码启用。"
            >
              <Field label="注册密码策略">
                <Select
                  value={form.registration.password_mode ?? "random"}
                  onValueChange={(value) =>
                    setForm({
                      ...form,
                      registration: {
                        ...form.registration,
                        password_mode: value as "none" | "random" | "fixed",
                      },
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">不设置密码</SelectItem>
                    <SelectItem value="random">每个账号随机生成</SelectItem>
                    <SelectItem value="fixed">统一固定密码</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              {form.registration.password_mode === "fixed" && (
                <Field className="mt-4" label="固定密码">
                  <div className="flex items-center gap-2">
                    <Input
                      autoComplete="new-password"
                      type={showFixedPassword ? "text" : "password"}
                      value={form.registration.fixed_password ?? ""}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          registration: {
                            ...form.registration,
                            fixed_password: event.target.value,
                          },
                        })
                      }
                    />
                    <Button
                      aria-label={showFixedPassword ? "隐藏密码" : "显示密码"}
                      onClick={() => setShowFixedPassword((value) => !value)}
                      size="icon"
                      title={showFixedPassword ? "隐藏密码" : "显示密码"}
                      type="button"
                      variant="outline"
                    >
                      {showFixedPassword ? <EyeOff /> : <Eye />}
                    </Button>
                    <Button
                      aria-label="随机生成固定密码"
                      onClick={() => {
                        const alphabet =
                          "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
                        const bytes = crypto.getRandomValues(new Uint8Array(20))
                        const password = Array.from(
                          bytes,
                          (value) => alphabet[value % alphabet.length]
                        ).join("")
                        setForm({
                          ...form,
                          registration: {
                            ...form.registration,
                            fixed_password: password,
                          },
                        })
                        setShowFixedPassword(true)
                      }}
                      size="icon"
                      title="随机生成固定密码"
                      type="button"
                      variant="outline"
                    >
                      <Dices />
                    </Button>
                  </div>
                </Field>
              )}
              <Toggle
                label="启用 Authenticator App MFA"
                checked={form.registration.enable_authenticator_mfa ?? false}
                onChange={(checked) =>
                  setForm({
                    ...form,
                    registration: {
                      ...form.registration,
                      enable_authenticator_mfa: checked,
                    },
                  })
                }
              />
              {form.registration.enable_authenticator_mfa && (
                <Field className="mt-4 max-w-xs" label="MFA 邮箱验证超时（秒）">
                  <Input
                    max={600}
                    min={30}
                    type="number"
                    value={form.registration.mfa_otp_timeout ?? 180}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        registration: {
                          ...form.registration,
                          mfa_otp_timeout: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
              )}
            </Section>
          </div>
        </TabsContent>

        <TabsContent className="mt-5 min-h-0 flex-1 overflow-auto" value="data">
          <DataTransferPanel />
        </TabsContent>

        <TabsContent
          className="mt-5 min-h-0 flex-1 overflow-auto"
          value="delivery"
        >
          <div className="mx-auto w-full max-w-5xl">
            <Section
              title="交付记录格式"
              description="支付链接与对应邮箱凭据按同一记录复制；单条复制与批量复制共用此模板。"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="序号格式">
                  <Select
                    value={form.delivery_copy.sequence_style ?? "chinese"}
                    onValueChange={(value) =>
                      setForm({
                        ...form,
                        delivery_copy: {
                          ...form.delivery_copy,
                          sequence_style:
                            value as DeliveryCopySettings["sequence_style"],
                        },
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">不显示序号</SelectItem>
                      <SelectItem value="number">1.</SelectItem>
                      <SelectItem value="chinese_number">第1个</SelectItem>
                      <SelectItem value="chinese">第一个</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="记录间隔">
                  <Select
                    value={form.delivery_copy.record_separator ?? "blank_line"}
                    onValueChange={(value) =>
                      setForm({
                        ...form,
                        delivery_copy: {
                          ...form.delivery_copy,
                          record_separator:
                            value as DeliveryCopySettings["record_separator"],
                        },
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="newline">换行</SelectItem>
                      <SelectItem value="blank_line">空一行</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="缺失字段处理">
                  <Select
                    value={form.delivery_copy.missing_policy ?? "placeholder"}
                    onValueChange={(value) =>
                      setForm({
                        ...form,
                        delivery_copy: {
                          ...form.delivery_copy,
                          missing_policy:
                            value as DeliveryCopySettings["missing_policy"],
                        },
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="placeholder">保留占位符</SelectItem>
                      <SelectItem value="skip">跳过整条记录</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="占位符">
                  <Input
                    disabled={form.delivery_copy.missing_policy === "skip"}
                    maxLength={16}
                    value={form.delivery_copy.placeholder ?? "-"}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        delivery_copy: {
                          ...form.delivery_copy,
                          placeholder: event.target.value,
                        },
                      })
                    }
                  />
                </Field>
              </div>
              <div className="mt-4">
                <Toggle
                  label="显示字段名称"
                  checked={form.delivery_copy.show_labels ?? false}
                  onChange={(checked) =>
                    setForm({
                      ...form,
                      delivery_copy: {
                        ...form.delivery_copy,
                        show_labels: checked,
                      },
                    })
                  }
                />
              </div>
            </Section>

            <Section title="模板行">
              <div className="grid gap-3">
                {(form.delivery_copy.rows ?? []).map((row, rowIndex) => (
                  <div className="border p-3" key={rowIndex}>
                    <div className="mb-3 flex items-center gap-2">
                      <span className="text-xs font-medium">
                        第 {rowIndex + 1} 行
                      </span>
                      <Input
                        aria-label={`第 ${rowIndex + 1} 行分隔符`}
                        className="ml-auto w-28 font-mono"
                        maxLength={32}
                        value={row.separator ?? " --- "}
                        onChange={(event) => {
                          const rows = [...(form.delivery_copy.rows ?? [])]
                          rows[rowIndex] = {
                            ...row,
                            separator: event.target.value,
                          }
                          setForm({
                            ...form,
                            delivery_copy: { ...form.delivery_copy, rows },
                          })
                        }}
                      />
                      <Button
                        aria-label={`删除第 ${rowIndex + 1} 行`}
                        disabled={(form.delivery_copy.rows?.length ?? 0) <= 1}
                        onClick={() => {
                          const rows = (form.delivery_copy.rows ?? []).filter(
                            (_, index) => index !== rowIndex
                          )
                          setForm({
                            ...form,
                            delivery_copy: { ...form.delivery_copy, rows },
                          })
                        }}
                        size="icon-sm"
                        variant="ghost"
                      >
                        <Trash2 />
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {row.fields.map((field, fieldIndex) => {
                        const label =
                          DELIVERY_FIELDS.find((item) => item.value === field)
                            ?.label ?? field
                        const move = (offset: number) => {
                          const fields = [...row.fields]
                          const target = fieldIndex + offset
                          ;[fields[fieldIndex], fields[target]] = [
                            fields[target],
                            fields[fieldIndex],
                          ]
                          const rows = [...(form.delivery_copy.rows ?? [])]
                          rows[rowIndex] = { ...row, fields }
                          setForm({
                            ...form,
                            delivery_copy: { ...form.delivery_copy, rows },
                          })
                        }
                        return (
                          <div
                            className="flex items-center border bg-muted/20"
                            key={`${field}-${fieldIndex}`}
                          >
                            <span className="px-2 text-xs">{label}</span>
                            <Button
                              aria-label={`${label}向前移动`}
                              disabled={fieldIndex === 0}
                              onClick={() => move(-1)}
                              size="icon-sm"
                              title="向前移动"
                              variant="ghost"
                            >
                              <ChevronLeft />
                            </Button>
                            <Button
                              aria-label={`${label}向后移动`}
                              disabled={fieldIndex === row.fields.length - 1}
                              onClick={() => move(1)}
                              size="icon-sm"
                              title="向后移动"
                              variant="ghost"
                            >
                              <ChevronRight />
                            </Button>
                            <Button
                              aria-label={`移除${label}`}
                              disabled={row.fields.length <= 1}
                              onClick={() => {
                                const rows = [
                                  ...(form.delivery_copy.rows ?? []),
                                ]
                                rows[rowIndex] = {
                                  ...row,
                                  fields: row.fields.filter(
                                    (_, index) => index !== fieldIndex
                                  ),
                                }
                                setForm({
                                  ...form,
                                  delivery_copy: {
                                    ...form.delivery_copy,
                                    rows,
                                  },
                                })
                              }}
                              size="icon-sm"
                              variant="ghost"
                            >
                              <Trash2 />
                            </Button>
                          </div>
                        )
                      })}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {DELIVERY_FIELDS.filter(
                        (field) => !row.fields.includes(field.value)
                      ).map((field) => (
                        <Button
                          key={field.value}
                          onClick={() => {
                            const rows = [...(form.delivery_copy.rows ?? [])]
                            rows[rowIndex] = {
                              ...row,
                              fields: [...row.fields, field.value],
                            }
                            setForm({
                              ...form,
                              delivery_copy: { ...form.delivery_copy, rows },
                            })
                          }}
                          size="sm"
                          variant="outline"
                        >
                          + {field.label}
                        </Button>
                      ))}
                    </div>
                  </div>
                ))}
                <Button
                  disabled={(form.delivery_copy.rows?.length ?? 0) >= 10}
                  onClick={() =>
                    setForm({
                      ...form,
                      delivery_copy: {
                        ...form.delivery_copy,
                        rows: [
                          ...(form.delivery_copy.rows ?? []),
                          { fields: ["email"], separator: " --- " },
                        ],
                      },
                    })
                  }
                  size="sm"
                  variant="outline"
                >
                  新增一行
                </Button>
              </div>
            </Section>

            <Section title="预览">
              <pre className="overflow-auto border bg-muted/20 p-4 font-mono text-xs whitespace-pre-wrap">
                {deliveryPreview(form.delivery_copy)}
              </pre>
            </Section>
          </div>
        </TabsContent>

        <TabsContent className="mt-5 min-h-0 flex-1 overflow-auto" value="mail">
          <div className="mx-auto w-full max-w-5xl">
            <Section
              title="邮箱来源"
              description="Outlook 模式从号池原子领取账号；Cloudflare 模式通过 cloudflare_temp_email Worker 自动创建邮箱，不消耗号池。"
            >
              <Field label="注册邮箱来源">
                <Select
                  value={form.mail.source ?? "outlook"}
                  onValueChange={(value) =>
                    setForm({
                      ...form,
                      mail: {
                        ...form.mail,
                        source: value as "outlook" | "cf_temp",
                      },
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="outlook">Outlook 号池</SelectItem>
                    <SelectItem value="cf_temp">Cloudflare 临时邮箱</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </Section>
            {form.mail.source === "cf_temp" && (
              <Section
                title="Cloudflare Worker"
                description="Worker URL、catch-all 收件域名和 ADMIN_PASSWORDS 管理密钥必须同时配置。连接测试会真实创建一个测试邮箱。"
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field className="sm:col-span-2" label="Worker URL">
                    <Input
                      placeholder="https://mail.example.com"
                      value={form.mail.cf_api_url ?? ""}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          mail: {
                            ...form.mail,
                            cf_api_url: event.target.value,
                          },
                        })
                      }
                    />
                  </Field>
                  <Field label="收件域名">
                    <Input
                      placeholder="example.com"
                      value={form.mail.cf_domain ?? ""}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          mail: { ...form.mail, cf_domain: event.target.value },
                        })
                      }
                    />
                  </Field>
                  <Field label="管理密钥">
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder="留空则保持原密钥"
                        type="password"
                        value={form.mail.cf_admin_token ?? ""}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            mail: {
                              ...form.mail,
                              cf_admin_token: event.target.value,
                            },
                          })
                        }
                      />
                      {settings.data?.mail.cf_admin_token_configured && (
                        <Badge className="shrink-0" variant="outline">
                          已配置
                        </Badge>
                      )}
                    </div>
                  </Field>
                </div>
                <div className="mt-4 flex justify-end">
                  <Button
                    disabled={mailTest.isPending}
                    onClick={() => mailTest.mutate()}
                    size="sm"
                    variant="outline"
                  >
                    <PlugZap />
                    测试连接
                  </Button>
                </div>
              </Section>
            )}
          </div>
        </TabsContent>

        <TabsContent
          className="mt-5 min-h-0 flex-1 overflow-auto"
          value="kakao"
        >
          <div className="mx-auto w-full max-w-5xl">
            <Section
              title="服务连接"
              description="单卡可用总次数同时扣除已扣卡和排队/提取中的任务；卡密分配前会查询上游实时用量，并扣除本地尚未提交的预留名额。"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field className="sm:col-span-2" label="Base URL">
                  <Input
                    value={form.kakao.base_url ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        kakao: { ...form.kakao, base_url: event.target.value },
                      })
                    }
                  />
                </Field>
                <Field label="请求超时（秒）">
                  <Input
                    max={300}
                    min={5}
                    type="number"
                    value={form.kakao.timeout ?? 30}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        kakao: {
                          ...form.kakao,
                          timeout: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
                <Field label="单卡可用总次数">
                  <Input
                    min={1}
                    type="number"
                    value={form.kakao.card_usage_limit ?? 10}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        kakao: {
                          ...form.kakao,
                          card_usage_limit: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
                <Field className="sm:col-span-2" label="Promo Code">
                  <Input
                    value={form.kakao.promo_code ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        kakao: {
                          ...form.kakao,
                          promo_code: event.target.value,
                        },
                      })
                    }
                  />
                </Field>
              </div>
              <div className="mt-4 flex justify-end">
                <Button
                  disabled={kakaoTest.isPending}
                  onClick={() => kakaoTest.mutate()}
                  size="sm"
                  variant="outline"
                >
                  <PlugZap />
                  测试连接
                </Button>
              </div>
            </Section>
          </div>
        </TabsContent>

        <TabsContent className="mt-5 min-h-0 flex-1 overflow-auto" value="sms">
          <div className="mx-auto w-full max-w-5xl">
            <Section
              title="接码服务"
              description="支持 SmsBower、HeroSMS 和 GrizzlySMS。自动选国只在候选国家中按库存与价格选择；同号复用受成功次数上限约束。"
            >
              <Toggle
                label="启用 SMS 接码"
                checked={form.sms.enabled ?? false}
                onChange={(checked) =>
                  setForm({ ...form, sms: { ...form.sms, enabled: checked } })
                }
              />
              <div className="mt-4 flex items-center justify-end gap-2">
                {smsTest.data && (
                  <Badge variant="outline">余额 {smsTest.data.balance}</Badge>
                )}
                <Button
                  disabled={smsTest.isPending}
                  onClick={() => smsTest.mutate()}
                  size="sm"
                  variant="outline"
                >
                  <PlugZap />
                  {smsTest.isPending ? "正在连接" : "测试余额"}
                </Button>
                <Button
                  disabled={smsCountries.isPending}
                  onClick={() => smsCountries.mutate()}
                  size="sm"
                  variant="outline"
                >
                  <RefreshCw />
                  {smsCountries.isPending ? "正在查询" : "查询国家库存"}
                </Button>
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field label="平台">
                  <Select
                    value={form.sms.provider ?? "smsbower"}
                    onValueChange={(value) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          provider: value as typeof form.sms.provider,
                        },
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="smsbower">SmsBower</SelectItem>
                      <SelectItem value="herosms">HeroSMS</SelectItem>
                      <SelectItem value="grizzlysms">GrizzlySMS</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="API Key">
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      value={form.sms.api_key ?? ""}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          sms: { ...form.sms, api_key: event.target.value },
                        })
                      }
                    />
                    {settings.data?.sms.api_key_configured && (
                      <Badge className="shrink-0" variant="outline">
                        已配置
                      </Badge>
                    )}
                  </div>
                </Field>
                <Field label="国家 ID">
                  <Input
                    value={form.sms.country ?? "52"}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: { ...form.sms, country: event.target.value },
                      })
                    }
                  />
                </Field>
                <Field label="服务代码">
                  <Input
                    value={form.sms.service ?? "dr"}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: { ...form.sms, service: event.target.value },
                      })
                    }
                  />
                </Field>
                <Field label="号码最高单价">
                  <Input
                    value={form.sms.max_price ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: { ...form.sms, max_price: event.target.value },
                      })
                    }
                  />
                </Field>
                <Field label="单号等待超时（秒）">
                  <Input
                    max={600}
                    min={40}
                    type="number"
                    value={form.sms.per_phone_timeout ?? 80}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          per_phone_timeout: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
                <Field label="最多尝试号码数">
                  <Input
                    max={20}
                    min={1}
                    type="number"
                    value={form.sms.max_phone_attempts ?? 3}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          max_phone_attempts: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
              </div>
            </Section>

            <Section title="号码复用">
              <Toggle
                label="启用号码复用"
                checked={form.sms.reuse_phone ?? false}
                onChange={(checked) =>
                  setForm({
                    ...form,
                    sms: { ...form.sms, reuse_phone: checked },
                  })
                }
              />
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field label="同号最多成功次数">
                  <Input
                    max={20}
                    min={1}
                    type="number"
                    value={form.sms.phone_success_max ?? 3}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          phone_success_max: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
              </div>
            </Section>

            <Section title="自动选择国家">
              <Toggle
                label="自动选择国家"
                checked={form.sms.auto_country ?? false}
                onChange={(checked) =>
                  setForm({
                    ...form,
                    sms: { ...form.sms, auto_country: checked },
                  })
                }
              />
              <Toggle
                label="仅限 OpenAI SMS 安全国家"
                checked={form.sms.strict_whitelist ?? false}
                onChange={(checked) =>
                  setForm({
                    ...form,
                    sms: { ...form.sms, strict_whitelist: checked },
                  })
                }
              />
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field
                  className="sm:col-span-2"
                  label="候选国家 ID（逗号分隔）"
                >
                  <Textarea
                    className="min-h-20 resize-y font-mono text-xs"
                    value={form.sms.allowed_countries ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          allowed_countries: event.target.value,
                        },
                      })
                    }
                  />
                </Field>
                <Field label="最低库存">
                  <Input
                    min={0}
                    type="number"
                    value={form.sms.auto_min_stock ?? 20}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          auto_min_stock: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
                <Field label="最高单价">
                  <Input
                    value={form.sms.auto_max_price ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        sms: {
                          ...form.sms,
                          auto_max_price: event.target.value,
                        },
                      })
                    }
                  />
                </Field>
              </div>
              {smsCountries.data && (
                <div className="mt-4 max-h-64 overflow-auto border-y py-2">
                  <div className="grid gap-x-4 sm:grid-cols-2 lg:grid-cols-3">
                    {smsCountries.data.items.map((country) => {
                      const selected = new Set(
                        (form.sms.allowed_countries ?? "")
                          .split(",")
                          .map((value) => value.trim())
                          .filter(Boolean)
                      )
                      return (
                        <label
                          className="flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs hover:bg-muted/50"
                          key={country.id}
                        >
                          <Checkbox
                            checked={selected.has(country.id)}
                            onCheckedChange={(checked) => {
                              if (checked) selected.add(country.id)
                              else selected.delete(country.id)
                              setForm({
                                ...form,
                                sms: {
                                  ...form.sms,
                                  allowed_countries: [...selected].join(","),
                                },
                              })
                            }}
                          />
                          <span className="truncate">
                            {country.id} · {country.name}
                          </span>
                          {country.safe && (
                            <Badge
                              className="ml-auto shrink-0"
                              variant="outline"
                            >
                              SMS
                            </Badge>
                          )}
                          {country.price != null && (
                            <span className="ml-auto shrink-0 text-muted-foreground">
                              {country.price} / {country.count ?? 0}
                            </span>
                          )}
                        </label>
                      )
                    })}
                  </div>
                </div>
              )}
            </Section>
          </div>
        </TabsContent>

        <TabsContent
          className="mt-5 min-h-0 flex-1 overflow-auto"
          value="export"
        >
          <div className="mx-auto w-full max-w-5xl">
            {(["cpa", "sub2api"] as const).map((target) => {
              const value = form.export[target] ?? {}
              const configured = settings.data?.export[target]?.key_configured
              return (
                <Section
                  key={target}
                  title={target === "cpa" ? "CPA" : "SUB2API"}
                  description={
                    target === "cpa"
                      ? "CPA 使用管理地址和 Management Key 上传 Codex 凭证文件。"
                      : "SUB2API 使用管理地址和 x-api-key 创建账号，可在下方指定 Group IDs。"
                  }
                >
                  <Toggle
                    label="启用自动导出"
                    checked={value.enabled ?? false}
                    onChange={(checked) =>
                      setForm({
                        ...form,
                        export: {
                          ...form.export,
                          [target]: { ...value, enabled: checked },
                        },
                      })
                    }
                  />
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <Field className="sm:col-span-2" label="URL">
                      <Input
                        value={value.url ?? ""}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            export: {
                              ...form.export,
                              [target]: { ...value, url: event.target.value },
                            },
                          })
                        }
                      />
                    </Field>
                    <Field label="密钥">
                      <div className="flex items-center gap-2">
                        <Input
                          type="password"
                          value={value.key ?? ""}
                          onChange={(event) =>
                            setForm({
                              ...form,
                              export: {
                                ...form.export,
                                [target]: { ...value, key: event.target.value },
                              },
                            })
                          }
                        />
                        {configured && (
                          <Badge className="shrink-0" variant="outline">
                            已配置
                          </Badge>
                        )}
                      </div>
                    </Field>
                    <Field label="请求超时（秒）">
                      <Input
                        max={300}
                        min={5}
                        type="number"
                        value={value.timeout ?? 30}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            export: {
                              ...form.export,
                              [target]: {
                                ...value,
                                timeout: Number(event.target.value),
                              },
                            },
                          })
                        }
                      />
                    </Field>
                  </div>
                  <div className="mt-4 flex justify-end">
                    <Button
                      disabled={exportTest.isPending}
                      onClick={() => exportTest.mutate(target)}
                      size="sm"
                      variant="outline"
                    >
                      <PlugZap />
                      测试连接
                    </Button>
                  </div>
                </Section>
              )
            })}
            <Section title="SUB2API 分组">
              <Field label="Group IDs">
                <Input
                  value={form.export.sub2api_group_ids ?? ""}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      export: {
                        ...form.export,
                        sub2api_group_ids: event.target.value,
                      },
                    })
                  }
                />
              </Field>
            </Section>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
