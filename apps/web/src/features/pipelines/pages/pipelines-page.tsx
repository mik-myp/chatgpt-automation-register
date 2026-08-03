import { useSearchParams } from "react-router"

import { CreateKakaoPipelineDialog } from "@/features/pipelines/components/create-kakao-dialog"
import { CreateRegistrationDialog } from "@/features/pipelines/components/create-registration-dialog"
import { CreateSecurityPipelineDialog } from "@/features/pipelines/components/create-security-dialog"
import { PipelineRunsList } from "@/features/pipelines/components/pipeline-runs-list"
import { TOUR_IDS } from "@/lib/product-tours"

export function PipelinesPage() {
  const [searchParams] = useSearchParams()

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div
        className="flex flex-wrap items-center justify-between gap-3"
        id={TOUR_IDS.pipelinesHeader}
      >
        <h1 className="text-xl font-semibold">流水线轮次</h1>
        <div
          className="flex flex-wrap items-center justify-end gap-2"
          id={TOUR_IDS.pipelineActions}
        >
          <CreateKakaoPipelineDialog />
          <CreateSecurityPipelineDialog />
          <div id={TOUR_IDS.createRegistration}>
            <CreateRegistrationDialog
              defaultEmail={searchParams.get("email") ?? ""}
            />
          </div>
        </div>
      </div>
      <div className="flex min-h-0 flex-1" id={TOUR_IDS.pipelineList}>
        <PipelineRunsList />
      </div>
    </div>
  )
}
