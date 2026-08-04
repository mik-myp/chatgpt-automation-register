import {
  getHealthApiHealthGetQueryKey,
  useHealthApiHealthGet,
} from "@/api/generated"

export function ApiStatus() {
  const health = useHealthApiHealthGet({
    query: {
      queryKey: getHealthApiHealthGetQueryKey(),
      refetchInterval: 10_000,
      retry: 1,
    },
  })

  const state = health.isPending
    ? { label: "正在连接", color: "bg-amber-500" }
    : health.isError
      ? { label: "API 未连接", color: "bg-destructive" }
      : { label: `API ${health.data.version}`, color: "bg-emerald-500" }

  return (
    <div
      className="ml-auto flex items-center gap-2 text-xs text-muted-foreground"
      role="status"
    >
      <span
        className={`size-2 rounded-full ${state.color}`}
        aria-hidden="true"
      />
      <span>{state.label}</span>
    </div>
  )
}
