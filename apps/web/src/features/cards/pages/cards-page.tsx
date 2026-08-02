import { useState } from "react"
import { Upload } from "lucide-react"

import { CardsInventory } from "@/features/cards/components/cards-inventory"
import { ImportCardsDialog } from "@/features/cards/components/card-tools"
import { Button } from "@workspace/ui/components/button"

export function CardsPage() {
  const [importOpen, setImportOpen] = useState(false)

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">卡密库存</h1>
        <Button onClick={() => setImportOpen(true)}>
          <Upload />
          导入卡密
        </Button>
      </div>
      <CardsInventory />
      <ImportCardsDialog open={importOpen} setOpen={setImportOpen} />
    </div>
  )
}
