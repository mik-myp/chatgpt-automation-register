import { useState } from "react"
import { Dices, Eye, EyeOff } from "lucide-react"

import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import {
  Field,
  Section,
  Toggle,
} from "@/features/settings/components/settings-fields"
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

export function RegistrationSettingsTab() {
  const { form, setForm } = useSettingsForm()
  const [showFixedPassword, setShowFixedPassword] = useState(false)
  return (
    <TabsContent
      className="mt-5 min-h-0 flex-1 overflow-auto"
      value="registration"
    >
      <div className="mx-auto w-full max-w-5xl">
        <Section
          title="运行参数"
          description="这里是批量流水线的注册协议默认值；新建轮次未填写覆盖值时自动继承。并发设置统一位于“流水线与代理”。"
        >
          <div className="max-w-xs">
            <Field label="OTP 超时（秒）">
              <Input
                max={300}
                min={1}
                type="number"
                value={form.registration.otp_timeout ?? 60}
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
  )
}
