import { useMutation } from "@tanstack/react-query"
import { PlugZap } from "lucide-react"
import { toast } from "sonner"

import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import { Field, Section } from "@/features/settings/components/settings-fields"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import { TabsContent } from "@workspace/ui/components/tabs"

export function MailSettingsTab() {
  const { form, settings, setForm } = useSettingsForm()
  const mailTest = useMutation<{ message: string }, ApiError>({
    mutationFn: () =>
      apiRequest<{ message: string }>("/api/settings/mail/test", {
        method: "POST",
      }),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  })
  return (
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
  )
}
