import { useMutation } from "@tanstack/react-query"
import { PlugZap } from "lucide-react"
import { toast } from "sonner"

import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import { Field, Section } from "@/features/settings/components/settings-fields"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { Switch } from "@workspace/ui/components/switch"
import { TabsContent } from "@workspace/ui/components/tabs"

export function KakaoSettingsTab() {
  const { form, setForm } = useSettingsForm()
  const kakaoTest = useMutation<{ message: string }, ApiError>({
    mutationFn: () =>
      apiRequest<{ message: string }>("/api/settings/kakao/test", {
        method: "POST",
      }),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  })
  return (
    <TabsContent className="mt-5 min-h-0 flex-1 overflow-auto" value="kakao">
      <div className="mx-auto w-full max-w-5xl">
        <Section
          title="本地提取引擎"
          description="Kakao 任务由本机直接执行 KR → VN → KR 支付流程。KR 和 VN 代理由全局代理 API 按账号尝试次数分别获取。"
        >
          <div className="grid gap-4 sm:grid-cols-2">
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
            <Field label="支付跳转轮询超时（秒）">
              <Input
                max={300}
                min={30}
                type="number"
                value={form.kakao.poll_timeout ?? 120}
                onChange={(event) =>
                  setForm({
                    ...form,
                    kakao: {
                      ...form.kakao,
                      poll_timeout: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
            <Field label="Promotion ID">
              <Input
                value={form.kakao.promo_code ?? "plus-1-month-free"}
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
            <label className="flex min-h-10 items-center justify-between gap-3 border-b text-sm">
              <span>强制校验 KR/VN 实际出口</span>
              <Switch
                checked={form.kakao.verify_proxy_countries ?? true}
                onCheckedChange={(checked) =>
                  setForm({
                    ...form,
                    kakao: {
                      ...form.kakao,
                      verify_proxy_countries: checked,
                    },
                  })
                }
              />
            </label>
          </div>
          <div className="mt-4 flex justify-end">
            <Button
              disabled={kakaoTest.isPending}
              onClick={() => kakaoTest.mutate()}
              size="sm"
              variant="outline"
            >
              <PlugZap />
              测试本地引擎
            </Button>
          </div>
        </Section>
      </div>
    </TabsContent>
  )
}
