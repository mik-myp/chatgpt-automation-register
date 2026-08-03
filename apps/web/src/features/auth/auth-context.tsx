import { useEffect, useMemo, useState, type ReactNode } from "react"
import { Navigate, Outlet, useLocation } from "react-router"

import { apiRequest, setCsrfToken } from "@/lib/api-client"
import { AuthContext, type AuthSession } from "./auth-state"

type SetupStatus = {
  initialized: boolean
  authentication_enabled: boolean
}

export function AuthGate() {
  const location = useLocation()
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "setup" }
    | { status: "login" }
    | { status: "ready"; session: AuthSession }
    | { status: "error"; message: string }
  >({ status: "loading" })

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const setup = await apiRequest<SetupStatus>("/setup/status")
        if (!active) return
        if (!setup.initialized && setup.authentication_enabled) {
          setState({ status: "setup" })
          return
        }
        const session = await apiRequest<AuthSession>("/auth/session")
        if (!active) return
        setCsrfToken(session.csrf_token)
        setState({ status: "ready", session })
      } catch (error) {
        if (!active) return
        const status = (error as { status?: number }).status
        if (status === 401) setState({ status: "login" })
        else
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "无法连接 API 服务",
          })
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const value = useMemo(
    () =>
      state.status === "ready"
        ? {
            session: state.session,
            clearSession: () => {
              setCsrfToken("")
              setState({ status: "login" })
            },
          }
        : null,
    [state]
  )

  if (state.status === "setup") return <Navigate to="/setup" replace />
  if (state.status === "login")
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (state.status === "error")
    return (
      <div className="grid min-h-svh place-items-center bg-background p-6 text-sm text-destructive">
        {state.message}
      </div>
    )
  if (state.status !== "ready" || value === null)
    return (
      <div className="grid min-h-svh place-items-center bg-background text-sm text-muted-foreground">
        正在验证会话...
      </div>
    )
  return (
    <AuthContext.Provider value={value}>
      <Outlet />
    </AuthContext.Provider>
  )
}

export function AuthPageShell({
  stage,
  title,
  description,
  children,
}: {
  stage: "setup" | "login"
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <main className="grid min-h-svh grid-rows-[auto_1fr] bg-background lg:grid-cols-[18rem_1fr] lg:grid-rows-1">
      <aside className="border-b bg-muted/30 px-6 py-5 lg:border-r lg:border-b-0 lg:px-8 lg:py-10">
        <div className="flex items-center gap-3 lg:items-start">
          <div className="mt-1 size-2 shrink-0 rounded-full bg-primary ring-4 ring-primary/10" />
          <div>
            <p className="text-sm font-medium">GPT Auto Register</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {stage === "setup" ? "首次初始化" : "管理员会话"}
            </p>
          </div>
        </div>
        <div className="mt-8 hidden border-l pl-5 text-xs text-muted-foreground lg:block">
          <p className={stage === "setup" ? "font-medium text-foreground" : ""}>
            01 初始化管理员
          </p>
          <p className={`mt-6 ${stage === "login" ? "font-medium text-foreground" : ""}`}>
            02 登录控制台
          </p>
          <p className="mt-6">03 运行流水线</p>
        </div>
      </aside>
      <section className="flex items-center px-6 py-12 sm:px-10 lg:px-20">
        <div className="w-full max-w-md">
          <p className="text-xs font-medium text-primary">
            {stage === "setup" ? "SETUP / 01" : "SESSION / 02"}
          </p>
          <h1 className="mt-3 text-2xl font-semibold tracking-normal">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </main>
  )
}
