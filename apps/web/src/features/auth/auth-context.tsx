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
            message:
              error instanceof Error ? error.message : "无法连接 API 服务",
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

export function AuthPageRoute({
  mode,
  children,
}: {
  mode: "setup" | "login"
  children: ReactNode
}) {
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "ready"; initialized: boolean; authenticated: boolean }
    | { status: "error"; message: string }
  >({ status: "loading" })

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const setup = await apiRequest<SetupStatus>("/setup/status")
        let authenticated = false
        if (mode === "login" && setup.initialized) {
          try {
            const session = await apiRequest<AuthSession>("/auth/session")
            setCsrfToken(session.csrf_token)
            authenticated = true
          } catch (error) {
            if ((error as { status?: number }).status !== 401) throw error
          }
        }
        if (active)
          setState({
            status: "ready",
            initialized: setup.initialized,
            authenticated,
          })
      } catch (error) {
        if (active)
          setState({
            status: "error",
            message:
              error instanceof Error ? error.message : "无法连接 API 服务",
          })
      }
    })()
    return () => {
      active = false
    }
  }, [mode])

  if (state.status === "loading")
    return (
      <div className="grid min-h-svh place-items-center bg-background text-sm text-muted-foreground">
        正在检查部署状态...
      </div>
    )
  if (state.status === "error")
    return (
      <div className="grid min-h-svh place-items-center bg-background p-6 text-sm text-destructive">
        {state.message}
      </div>
    )
  if (mode === "setup" && state.initialized)
    return <Navigate to="/login" replace />
  if (mode === "login" && !state.initialized)
    return <Navigate to="/setup" replace />
  if (mode === "login" && state.authenticated)
    return <Navigate to="/" replace />
  return children
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
  if (stage === "login") {
    return (
      <main className="grid min-h-svh grid-rows-[auto_1fr] bg-background">
        <header className="flex h-16 items-center border-b px-6 sm:px-10">
          <div className="flex items-center gap-3">
            <div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
              <span className="text-xs font-semibold">GA</span>
            </div>
            <div className="leading-tight">
              <p className="text-sm font-medium">GPT Auto Register</p>
              <p className="text-xs text-muted-foreground">账户登录</p>
            </div>
          </div>
        </header>
        <section className="flex items-center justify-center px-6 py-12">
          <div className="w-full max-w-sm">
            <p className="text-xs font-medium text-primary">WELCOME BACK</p>
            <h1 className="mt-3 text-2xl font-semibold tracking-normal">
              {title}
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {description}
            </p>
            <div className="mt-8">{children}</div>
          </div>
        </section>
      </main>
    )
  }

  return (
    <main className="grid min-h-svh grid-rows-[auto_1fr] bg-background lg:grid-cols-[20rem_1fr] lg:grid-rows-1">
      <aside className="border-b bg-emerald-950 px-6 py-6 text-white lg:border-r lg:border-b-0 lg:px-8 lg:py-10">
        <div className="flex items-center gap-3 lg:items-start">
          <div className="mt-1 size-2 shrink-0 rounded-full bg-emerald-300 ring-4 ring-emerald-300/15" />
          <div>
            <p className="text-sm font-medium">GPT Auto Register</p>
            <p className="mt-1 text-xs text-emerald-100/70">首次部署向导</p>
          </div>
        </div>
        <div className="mt-10 hidden border-l border-emerald-700 pl-5 text-xs text-emerald-100/60 lg:block">
          <p className="font-medium text-white">01 创建管理员</p>
          <p className="mt-6">02 验证运行环境</p>
          <p className="mt-6">03 进入工作台</p>
        </div>
      </aside>
      <section className="flex items-center px-6 py-12 sm:px-10 lg:px-20">
        <div className="w-full max-w-md">
          <p className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
            INITIAL SETUP
          </p>
          <h1 className="mt-3 text-2xl font-semibold tracking-normal">
            {title}
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {description}
          </p>
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </main>
  )
}
