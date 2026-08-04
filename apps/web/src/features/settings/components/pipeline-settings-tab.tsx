import { useMutation } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, PlugZap } from "lucide-react"
import { toast } from "sonner"

import type { PipelineSettingsStepOrderItem } from "@/api/generated"
import { Field, Section } from "@/features/settings/components/settings-fields"
import { useSettingsForm } from "@/features/settings/components/settings-form-state"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { TabsContent } from "@workspace/ui/components/tabs"

const DEFAULT_ORDER: PipelineSettingsStepOrderItem[] = [
  "registration",
  "account_security",
  "kakao",
]

const STEP_LABELS: Record<PipelineSettingsStepOrderItem, string> = {
  registration: "注册",
  account_security: "设置密码与 MFA",
  kakao: "创建 Kakao 并提取支付链接",
}

export function PipelineSettingsTab() {
  const { form, setForm } = useSettingsForm()
  const proxy = form.proxy ?? {}
  const pipeline = form.pipeline ?? {}
  const order = pipeline.step_order ?? DEFAULT_ORDER
  const proxyTest = useMutation<{ message: string }, ApiError>({
    mutationFn: () =>
      apiRequest<{ message: string }>("/api/settings/proxy/test", {
        method: "POST",
      }),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  })

  const updatePipeline = (values: Partial<typeof pipeline>) =>
    setForm({ ...form, pipeline: { ...pipeline, ...values } })
  const moveStep = (index: number, direction: -1 | 1) => {
    const destination = index + direction
    if (destination < 0 || destination >= order.length) return
    const next = [...order]
    ;[next[index], next[destination]] = [next[destination], next[index]]
    updatePipeline({ step_order: next })
  }

  return (
    <TabsContent className="mt-5 min-h-0 flex-1 overflow-auto" value="pipeline">
      <div className="mx-auto w-full max-w-5xl">
        <Section
          title="动态代理"
          description="每次任务按邮箱数乘以单账号尝试次数请求代理。Kakao 会分别请求等量 KR、VN 代理并按相同位置组成代理对；未获得完整代理组的账号不会开始执行。"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field className="sm:col-span-2" label="代理 API 链接地址">
              <Input
                placeholder="https://proxy.example.com/get?num={count}"
                value={proxy.api_url ?? ""}
                onChange={(event) =>
                  setForm({
                    ...form,
                    proxy: { ...proxy, api_url: event.target.value },
                  })
                }
              />
            </Field>
            <Field label="单账号最大代理尝试次数（含首次尝试）">
              <Input
                min={1}
                max={10}
                type="number"
                value={proxy.max_attempts_per_account ?? 3}
                onChange={(event) =>
                  setForm({
                    ...form,
                    proxy: {
                      ...proxy,
                      max_attempts_per_account: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
            <Field label="代理 API 请求超时（秒）">
              <Input
                min={5}
                max={120}
                type="number"
                value={proxy.request_timeout ?? 30}
                onChange={(event) =>
                  setForm({
                    ...form,
                    proxy: {
                      ...proxy,
                      request_timeout: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
          </div>
          <div className="mt-4 flex justify-end">
            <Button
              disabled={proxyTest.isPending || !proxy.api_url?.trim()}
              onClick={() => proxyTest.mutate()}
              size="sm"
              type="button"
              variant="outline"
            >
              <PlugZap />
              测试代理 API
            </Button>
          </div>
        </Section>

        <Section
          title="流水线步骤顺序"
          description="同一批等待任务严格按此步骤优先级调度。执行器会校验账号凭据和 Access Token 等前置条件，不满足条件时记录跳过或失败原因。"
        >
          <ol className="divide-y border-y">
            {order.map((step, index) => (
              <li className="flex min-h-14 items-center gap-3 py-2" key={step}>
                <span className="w-6 text-center font-mono text-xs text-muted-foreground">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 text-sm font-medium">
                  {STEP_LABELS[step]}
                </span>
                <Button
                  aria-label={`上移${STEP_LABELS[step]}`}
                  disabled={index === 0}
                  onClick={() => moveStep(index, -1)}
                  size="icon"
                  title="上移"
                  type="button"
                  variant="ghost"
                >
                  <ArrowUp />
                </Button>
                <Button
                  aria-label={`下移${STEP_LABELS[step]}`}
                  disabled={index === order.length - 1}
                  onClick={() => moveStep(index, 1)}
                  size="icon"
                  title="下移"
                  type="button"
                  variant="ghost"
                >
                  <ArrowDown />
                </Button>
              </li>
            ))}
          </ol>
        </Section>

        <Section
          title="任务级并发"
          description="控制同一时间可运行多少个同类型任务；达到上限的任务保留在全局等待队列。"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <ConcurrencyField
              label="注册任务并发数"
              value={pipeline.registration_task_concurrency ?? 1}
              onChange={(value) =>
                updatePipeline({ registration_task_concurrency: value })
              }
              max={20}
            />
            <ConcurrencyField
              label="设置密码与 MFA 任务并发数"
              value={pipeline.account_security_task_concurrency ?? 1}
              onChange={(value) =>
                updatePipeline({ account_security_task_concurrency: value })
              }
              max={20}
            />
            <ConcurrencyField
              label="创建 Kakao 任务并发数"
              value={pipeline.kakao_task_concurrency ?? 1}
              onChange={(value) =>
                updatePipeline({ kakao_task_concurrency: value })
              }
              max={20}
            />
          </div>
        </Section>

        <Section
          title="邮箱级并发"
          description="控制单个任务内部同时处理多少个邮箱账号，与上方任务级并发同时生效。"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <ConcurrencyField
              label="单个注册任务邮箱级并发数"
              value={form.registration.concurrency ?? 10}
              onChange={(value) =>
                setForm({
                  ...form,
                  registration: { ...form.registration, concurrency: value },
                })
              }
              max={50}
            />
            <ConcurrencyField
              label="单个密码与 MFA 任务邮箱级并发数"
              value={pipeline.account_security_email_concurrency ?? 10}
              onChange={(value) =>
                updatePipeline({ account_security_email_concurrency: value })
              }
              max={50}
            />
            <ConcurrencyField
              label="单个 Kakao 任务邮箱级并发数"
              value={pipeline.kakao_email_concurrency ?? 10}
              onChange={(value) =>
                updatePipeline({ kakao_email_concurrency: value })
              }
              max={50}
            />
          </div>
        </Section>
      </div>
    </TabsContent>
  )
}

function ConcurrencyField({
  label,
  value,
  onChange,
  max,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  max: number
}) {
  return (
    <Field label={label}>
      <Input
        min={1}
        max={max}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  )
}
