import { useEffect, useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import { ShieldCheckIcon } from "lucide-react"

import { AuthPageShell } from "./auth-context"
import type { AuthSession } from "./auth-state"
import { apiRequest, setCsrfToken } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"

export function SetupPage() {
  const navigate = useNavigate()
  const [token, setToken] = useState("")
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)

  useEffect(() => {
    void apiRequest<{ initialized: boolean }>("/setup/status").then((status) => {
      if (status.initialized) navigate("/login", { replace: true })
    })
  }, [navigate])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (password !== confirm) {
      setError("两次输入的密码不一致")
      return
    }
    setPending(true)
    setError("")
    try {
      const session = await apiRequest<AuthSession>("/setup/initialize", {
        method: "POST",
        data: { token, username, password },
      })
      setCsrfToken(session.csrf_token)
      window.location.assign("/")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "初始化失败")
      setPending(false)
    }
  }

  return (
    <AuthPageShell
      stage="setup"
      title="创建管理员"
      description="初始化令牌会在 API 首次启动日志中显示，并在 30 分钟后失效。"
    >
      <form className="space-y-5" onSubmit={submit}>
        <div className="space-y-2">
          <Label htmlFor="setup-token">初始化令牌</Label>
          <Input
            id="setup-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="setup-username">管理员用户名</Label>
          <Input
            id="setup-username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="setup-password">密码</Label>
            <Input
              id="setup-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="setup-confirm">确认密码</Label>
            <Input
              id="setup-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </div>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button className="w-full" size="lg" disabled={pending}>
          <ShieldCheckIcon />
          {pending ? "正在初始化..." : "完成初始化"}
        </Button>
      </form>
    </AuthPageShell>
  )
}
