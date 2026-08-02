import { useMutation } from "@tanstack/react-query"
import { PlugZap, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import {
  Field,
  Section,
  type SmsCountryResponse,
  Toggle,
} from "@/features/settings/components/settings-fields"
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
import { TabsContent } from "@workspace/ui/components/tabs"
import { Textarea } from "@workspace/ui/components/textarea"

export function SmsSettingsTab() {
  const { form, settings, setForm } = useSettingsForm()
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
  return (
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
            <Field className="sm:col-span-2" label="候选国家 ID（逗号分隔）">
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
                        <Badge className="ml-auto shrink-0" variant="outline">
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
  )
}
