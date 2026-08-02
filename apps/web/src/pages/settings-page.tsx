import { type ReactNode, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import {
  Dices,
  Eye,
  EyeOff,
  PlugZap,
  RefreshCw,
  Save,
} from "lucide-react"
import { toast } from "sonner"

import {
  type SystemSettingsResponse,
  type SystemSettingsUpdate,
  useGetSettingsApiSettingsGet,
  useUpdateSettingsApiSettingsPut,
} from "@/api/generated"
import { DataTransferPanel } from "@/components/settings/data-transfer-panel"
import { DeliveryCopyPanel } from "@/components/settings/delivery-copy-panel"
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
      payment_links: {
        ...settings.delivery_copy.payment_links,
        rows: settings.delivery_copy.payment_links?.rows?.map((row) => ({
          ...row,
          fields: [...row.fields],
        })),
      },
      account_info: {
        ...settings.delivery_copy.account_info,
        rows: settings.delivery_copy.account_info?.rows?.map((row) => ({
          ...row,
          fields: [...row.fields],
        })),
      },
    },
    maintenance: { ...settings.maintenance },
  }
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
        <TabsList className="w-full shrink-0 justify-start">
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
          <DataTransferPanel
            maintenance={
              form.maintenance ?? {
                job_log_retention_days: 14,
                max_runtime_log_lines: 2000,
              }
            }
            onMaintenanceChange={(maintenance) =>
              setForm({ ...form, maintenance })
            }
          />
        </TabsContent>
        <TabsContent
          className="mt-5 min-h-0 flex-1 overflow-auto"
          value="delivery"
        >
          <DeliveryCopyPanel
            value={form.delivery_copy}
            onChange={(delivery_copy) => setForm({ ...form, delivery_copy })}
          />
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
