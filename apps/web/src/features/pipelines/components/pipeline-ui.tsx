import { Clipboard, X } from "lucide-react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/status-badge"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"

export function SelectionCheckbox({
  ids,
  selected,
  setSelected,
}: {
  ids: string[]
  selected: string[]
  setSelected: (ids: string[]) => void
}) {
  const count = ids.filter((id) => selected.includes(id)).length
  return (
    <Checkbox
      aria-label="选择当前表格全部行"
      checked={
        ids.length > 0 && count === ids.length
          ? true
          : count > 0
            ? "indeterminate"
            : false
      }
      onCheckedChange={(checked) => setSelected(checked ? ids : [])}
    />
  )
}

export function RowCheckbox({
  id,
  selected,
  setSelected,
}: {
  id: string
  selected: string[]
  setSelected: (ids: string[]) => void
}) {
  return (
    <Checkbox
      aria-label={`选择 ${id}`}
      checked={selected.includes(id)}
      onCheckedChange={() =>
        setSelected(
          selected.includes(id)
            ? selected.filter((value) => value !== id)
            : [...selected, id]
        )
      }
    />
  )
}

async function copyValues(values: string[], label: string) {
  await navigator.clipboard.writeText(values.join("\n"))
  toast.success(`已复制 ${values.length} 个${label}`)
}

export function CopySelectionBar({
  selected,
  values,
  label,
  clear,
}: {
  selected: string[]
  values: string[]
  label: string
  clear: () => void
}) {
  if (!selected.length) return null
  return (
    <div className="flex items-center justify-end gap-2">
      <span className="text-xs font-medium">已选 {selected.length} 项</span>
      <Button
        onClick={() => void copyValues(values, label)}
        size="sm"
        variant="outline"
      >
        <Clipboard />
        复制{label}
      </Button>
      <Button
        aria-label="清除选择"
        onClick={clear}
        size="icon-sm"
        variant="ghost"
      >
        <X />
      </Button>
    </div>
  )
}

export function PlusStateBadge({
  state,
  label,
  error,
}: {
  state?: string | null
  label?: string | null
  error?: string | null
}) {
  return (
    <span title={error || undefined}>
      <StatusBadge status={state || "unknown"} label={label || "未检查"} />
    </span>
  )
}
