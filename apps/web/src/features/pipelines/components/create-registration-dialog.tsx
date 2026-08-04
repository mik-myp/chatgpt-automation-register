import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { toast } from "sonner"

import {
  type PipelineRunSummary,
  useGetSettingsApiSettingsGet,
} from "@/api/generated"
import { ApiError, apiRequest } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"

type PipelineRunCreateRequest = {
  mode: "single" | "batch"
  email: string
  target_count: number
  concurrency: number | null
  otp_timeout: number | null
  kakao_enabled: boolean
}

export function CreateRegistrationDialog({
  defaultEmail,
}: {
  defaultEmail: string
}) {
  const queryClient = useQueryClient()
  const settings = useGetSettingsApiSettingsGet()
  const [open, setOpen] = useState(Boolean(defaultEmail))
  const [mode, setMode] = useState<"single" | "batch">(
    defaultEmail ? "single" : "batch"
  )
  const [targetCount, setTargetCount] = useState(20)
  const [concurrency, setConcurrency] = useState("")
  const [otpTimeout, setOtpTimeout] = useState("")
  const mutation = useMutation<
    PipelineRunSummary,
    ApiError,
    PipelineRunCreateRequest
  >({
    mutationFn: (data) =>
      apiRequest<PipelineRunSummary>("/api/pipelines/runs", {
        method: "POST",
        data,
      }),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({
        queryKey: ["/api/pipelines/runs"],
      })
      void queryClient.invalidateQueries({ queryKey: ["/api/dashboard"] })
      setOpen(false)
      toast.success(
        `已创建${mode === "single" ? "单次注册" : "批量轮次"} ${run.id}`
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const defaults = settings.data?.registration
  const numberOrNull = (value: string) => (value.trim() ? Number(value) : null)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          新建注册
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>新建注册</DialogTitle>
          <DialogDescription>
            单次注册由系统自动选择邮箱，批量注册按目标数量创建流水线。
          </DialogDescription>
        </DialogHeader>

        <Tabs
          className="min-w-0"
          value={mode}
          onValueChange={(value) => setMode(value as typeof mode)}
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="single">单次注册</TabsTrigger>
            <TabsTrigger value="batch">批量流水线</TabsTrigger>
          </TabsList>
          <TabsContent className="mt-4" value="single">
            <div className="border-y py-4 text-sm text-muted-foreground">
              Outlook 模式从号池领取一个可用账号；Cloudflare
              模式自动创建临时邮箱。
            </div>
          </TabsContent>
          <TabsContent className="mt-4 space-y-5" value="batch">
            <section className="grid gap-4 border-y py-4 sm:grid-cols-3">
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                目标数量
                <Input
                  max={10000}
                  min={1}
                  onChange={(event) =>
                    setTargetCount(Math.max(1, Number(event.target.value)))
                  }
                  type="number"
                  value={targetCount}
                />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                并发数
                <Input
                  max={50}
                  min={1}
                  onChange={(event) => setConcurrency(event.target.value)}
                  placeholder={`系统设置：${defaults?.concurrency ?? 10}`}
                  type="number"
                  value={concurrency}
                />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">
                OTP 超时（秒）
                <Input
                  max={300}
                  min={1}
                  onChange={(event) => setOtpTimeout(event.target.value)}
                  placeholder={`系统设置：${defaults?.otp_timeout ?? 60}`}
                  type="number"
                  value={otpTimeout}
                />
              </label>
            </section>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate({
                mode,
                email: mode === "single" ? defaultEmail : "",
                target_count: mode === "single" ? 1 : targetCount,
                concurrency:
                  mode === "batch" ? numberOrNull(concurrency) : null,
                otp_timeout: mode === "batch" ? numberOrNull(otpTimeout) : null,
                kakao_enabled: false,
              })
            }
          >
            <Plus />
            {mutation.isPending ? "正在创建" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
