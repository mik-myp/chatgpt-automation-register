import { useState, type FormEvent } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { PlusIcon, RefreshCcwIcon, UsersIcon } from "lucide-react"
import { toast } from "sonner"

import {
  getListUsersApiUsersGetQueryKey,
  useCreateUserApiUsersPost,
  useListUsersApiUsersGet,
  useUpdateUserApiUsersUserIdPatch,
  type UserRole,
} from "@/api/generated"
import { ApiError } from "@/lib/api-client"
import { formatCompactBeijingDateTime } from "@/lib/date-time"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@workspace/ui/components/dialog"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import { Switch } from "@workspace/ui/components/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@workspace/ui/components/table"

export function UsersPage() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [role, setRole] = useState<UserRole>("user")
  const [formError, setFormError] = useState("")

  const users = useListUsersApiUsersGet()
  const usersQueryKey = getListUsersApiUsersGetQueryKey()

  const updateUser = useUpdateUserApiUsersUserIdPatch<ApiError>({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: usersQueryKey })
      },
      onError: (error) => toast.error(error.message),
    },
  })

  const createUser = useCreateUserApiUsersPost<ApiError>({
    mutation: {
      onSuccess: () => {
        toast.success("用户已创建")
        setCreateOpen(false)
        setUsername("")
        setPassword("")
        setRole("user")
        setFormError("")
        void queryClient.invalidateQueries({ queryKey: usersQueryKey })
      },
      onError: (error) => setFormError(error.message),
    },
  })

  function submitCreate(event: FormEvent) {
    event.preventDefault()
    setFormError("")
    if (!/^[A-Za-z0-9_.-]{3,128}$/.test(username)) {
      setFormError("用户名至少 3 位，且只能包含字母、数字、点、短横线和下划线")
      return
    }
    if (password.length < 6) {
      setFormError("密码至少需要 6 位")
      return
    }
    createUser.mutate({ data: { username, password, role } })
  }

  const activeCount =
    users.data?.items.filter((user) => user.active).length ?? 0
  const adminCount =
    users.data?.items.filter((user) => user.role === "admin").length ?? 0

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">用户管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理可登录工作台的账户与角色。
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon />
          新增用户
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-y py-3 text-sm">
        <span className="flex items-center gap-2 text-muted-foreground">
          <UsersIcon className="size-4 text-teal-600 dark:text-teal-400" />
          用户总数{" "}
          <strong className="font-medium text-foreground">
            {users.data?.total ?? 0}
          </strong>
        </span>
        <span className="text-muted-foreground">
          启用{" "}
          <strong className="font-medium text-foreground">{activeCount}</strong>
        </span>
        <span className="text-muted-foreground">
          管理员{" "}
          <strong className="font-medium text-foreground">{adminCount}</strong>
        </span>
      </div>

      <section aria-label="用户列表" className="min-h-0 flex-1 overflow-auto">
        <Table className="min-w-180">
          <TableHeader>
            <TableRow>
              <TableHead>用户名</TableHead>
              <TableHead className="w-40">角色</TableHead>
              <TableHead className="w-32">状态</TableHead>
              <TableHead className="w-48">创建时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.isLoading &&
              Array.from({ length: 4 }, (_, index) => (
                <TableRow key={index}>
                  <TableCell colSpan={4}>
                    <div className="h-5 animate-pulse rounded bg-muted" />
                  </TableCell>
                </TableRow>
              ))}
            {users.isError && (
              <TableRow>
                <TableCell className="h-52 text-center" colSpan={4}>
                  <p className="text-sm font-medium">无法读取用户列表</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {users.error instanceof Error
                      ? users.error.message
                      : "发生未知错误"}
                  </p>
                  <Button
                    className="mt-4"
                    onClick={() => users.refetch()}
                    size="sm"
                    variant="outline"
                  >
                    <RefreshCcwIcon />
                    重新加载
                  </Button>
                </TableCell>
              </TableRow>
            )}
            {users.data?.items.map((user) => (
              <TableRow key={user.id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{user.username}</span>
                    <Badge
                      className={
                        user.role === "admin"
                          ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300"
                          : ""
                      }
                      variant={user.role === "admin" ? "outline" : "secondary"}
                    >
                      {user.role === "admin" ? "管理员" : "普通用户"}
                    </Badge>
                  </div>
                </TableCell>
                <TableCell>
                  <Select
                    disabled={updateUser.isPending}
                    value={user.role}
                    onValueChange={(value: UserRole) =>
                      updateUser.mutate({
                        userId: user.id,
                        data: { role: value },
                      })
                    }
                  >
                    <SelectTrigger
                      aria-label={`${user.username} 的角色`}
                      className="w-28"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">管理员</SelectItem>
                      <SelectItem value="user">普通用户</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Switch
                      aria-label={`${user.username} 的启用状态`}
                      checked={user.active}
                      disabled={updateUser.isPending}
                      onCheckedChange={(active) =>
                        updateUser.mutate({
                          userId: user.id,
                          data: { active },
                        })
                      }
                    />
                    <span className="text-xs text-muted-foreground">
                      {user.active ? "启用" : "停用"}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatCompactBeijingDateTime(user.created_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) setFormError("")
        }}
      >
        <DialogContent>
          <form onSubmit={submitCreate}>
            <DialogHeader>
              <DialogTitle>新增用户</DialogTitle>
              <DialogDescription>
                创建一个可登录工作台的账户。
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-5">
              <div className="space-y-2">
                <Label htmlFor="new-username">用户名</Label>
                <Input
                  id="new-username"
                  autoComplete="off"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-user-password">初始密码</Label>
                <Input
                  id="new-user-password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">至少 6 位</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-user-role">角色</Label>
                <Select
                  value={role}
                  onValueChange={(value: UserRole) => setRole(value)}
                >
                  <SelectTrigger id="new-user-role" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="user">普通用户</SelectItem>
                    <SelectItem value="admin">管理员</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {formError ? (
                <p className="text-sm text-destructive">{formError}</p>
              ) : null}
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateOpen(false)}
              >
                取消
              </Button>
              <Button disabled={createUser.isPending} type="submit">
                {createUser.isPending ? "正在创建..." : "创建用户"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
