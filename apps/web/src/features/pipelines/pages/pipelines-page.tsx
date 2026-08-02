import { useSearchParams } from "react-router"

import { CreateKakaoPipelineDialog } from "@/features/pipelines/components/create-kakao-dialog"
import { CreateRegistrationDialog } from "@/features/pipelines/components/create-registration-dialog"
import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import { PipelineRunsList } from "@/features/pipelines/components/pipeline-runs-list"

export function PipelinesPage() {
  const [searchParams] = useSearchParams()

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">流水线轮次</h1>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <CreateKakaoPipelineDialog />
          <CreateSecurityPipelineDialog />
          <CreateRegistrationDialog
            defaultEmail={searchParams.get("email") ?? ""}
          />
        </div>
      </div>
      <PipelineRunsList />
    </div>
  )
}
