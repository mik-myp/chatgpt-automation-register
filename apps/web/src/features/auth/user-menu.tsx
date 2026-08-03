import { useState, type FormEvent } from "react"
import { KeyRoundIcon, LogOutIcon, UserRoundIcon } from "lucide-react"

import { useAuth } from "./auth-state"
import { apiRequest } from "@/lib/api-client"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@workspace/ui/components/dropdown-menu"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"

export function UserMenu() {
  const { session, clearSession } = useAuth()
  const [open, setOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [error, setError] = useState("")

  async function logout() {
    await apiRequest("/auth/logout", { method: "POST" })
    clearSession()
    window.location.assign("/login")
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setError("")
    try {
      await apiRequest("/auth/change-password", {
        method: "POST",
        data: { current_password: currentPassword, new_password: newPassword },
      })
      clearSession()
      window.location.assign("/login")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "修改密码失败")
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" title="管理员菜单">
            <UserRoundIcon />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>{session.username}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setOpen(true)}>
            <KeyRoundIcon />
            修改密码
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => void logout()}>
            <LogOutIcon />
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <form onSubmit={changePassword}>
            <DialogHeader>
              <DialogTitle>修改管理员密码</DialogTitle>
              <DialogDescription>保存后会撤销全部登录会话。</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-5">
              <div className="space-y-2">
                <Label htmlFor="current-password">当前密码</Label>
                <Input
                  id="current-password"
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-password">新密码</Label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                />
              </div>
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                取消
              </Button>
              <Button type="submit">保存密码</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
