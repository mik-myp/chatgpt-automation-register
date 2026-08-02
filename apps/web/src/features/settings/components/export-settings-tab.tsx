import { useMutation } from "@tanstack/react-query"
import { PlugZap } from "lucide-react"
import { toast } from "sonner"

import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import {
  Field,
  Section,
  Toggle,
} from "@/features/settings/components/settings-fields"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { TabsContent } from "@workspace/ui/components/tabs"

export function ExportSettingsTab() {
  const { form, settings, setForm } = useSettingsForm()
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
  return (
    <TabsContent className="mt-5 min-h-0 flex-1 overflow-auto" value="export">
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
  )
}
