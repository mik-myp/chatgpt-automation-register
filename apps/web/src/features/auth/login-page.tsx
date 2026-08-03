import { useEffect, useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import { LogInIcon } from "lucide-react"

import { AuthPageShell } from "./auth-context"
import type { AuthSession } from "./auth-state"
import { apiRequest, setCsrfToken } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"

export function LoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)

  useEffect(() => {
    void apiRequest<{ initialized: boolean }>("/setup/status").then((status) => {
      if (!status.initialized) navigate("/setup", { replace: true })
    })
  }, [navigate])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError("")
    try {
      const session = await apiRequest<AuthSession>("/auth/login", {
        method: "POST",
        data: { username, password },
      })
      setCsrfToken(session.csrf_token)
      window.location.assign("/")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登录失败")
      setPending(false)
    }
  }

  return (
    <AuthPageShell
      stage="login"
      title="登录控制台"
      description="使用初始化时创建的管理员账号继续。"
    >
      <form className="space-y-5" onSubmit={submit}>
        <div className="space-y-2">
          <Label htmlFor="username">用户名</Label>
          <Input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">密码</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button className="w-full" size="lg" disabled={pending}>
          <LogInIcon />
          {pending ? "正在登录..." : "登录"}
        </Button>
      </form>
    </AuthPageShell>
  )
}
