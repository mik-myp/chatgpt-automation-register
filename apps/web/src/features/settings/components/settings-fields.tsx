import type { ReactNode } from "react"

import { Switch } from "@workspace/ui/components/switch"

export type SmsCountryResponse = {
  items: Array<{
    id: string
    name: string
    safe: boolean
    price: number | null
    count: number | null
  }>
  live: boolean
}

export function Field({
  label,
  className = "",
  children,
}: {
  label: string
  className?: string
  children: ReactNode
}) {
  return (
    <label
      className={`grid gap-1.5 text-xs text-muted-foreground ${className}`}
    >
      <span>{label}</span>
      {children}
    </label>
  )
}

export function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="border-t py-5 first:border-t-0 first:pt-0 last:border-b">
      <h2 className="mb-4 text-sm font-semibold">{title}</h2>
      {description && (
        <p className="-mt-2 mb-4 max-w-3xl text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      )}
      {children}
    </section>
  )
}

export function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex min-h-11 items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0">
      <span>{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  )
}
