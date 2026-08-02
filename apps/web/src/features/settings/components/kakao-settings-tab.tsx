import { useMutation } from "@tanstack/react-query"
import { PlugZap } from "lucide-react"
import { toast } from "sonner"

import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import { Field, Section } from "@/features/settings/components/settings-fields"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
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
  )
}
