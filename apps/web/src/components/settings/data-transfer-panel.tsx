import { type ReactNode, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Database, Download, FileArchive, Upload } from "lucide-react"
import { toast } from "sonner"

import {
  type BackupBundle,
  type BackupPreviewResponse,
  type MaintenanceSettings,
  useGetStorageStatsApiSettingsDataStorageGet,
} from "@/api/generated"
import { ApiError, apiRequest } from "@/lib/api-client"
import {
  decryptBackup,
  encryptBackup,
  isEncryptedBackup,
} from "@/lib/backup-crypto"
import { Button } from "@workspace/ui/components/button"
import { Checkbox } from "@workspace/ui/components/checkbox"
import { Input } from "@workspace/ui/components/input"
import { Separator } from "@workspace/ui/components/separator"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-xs text-muted-foreground">
      <span>{label}</span>
      {children}
    </label>
  )
}

function Section({
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

const BACKUP_SECTIONS = [
  ["settings", "系统配置"],
  ["accounts", "邮箱号池"],
  ["credentials", "注册凭据"],
  ["card_batches", "卡密批次"],
  ["cards", "卡密"],
] as const

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export function DataTransferPanel({
  maintenance,
  onMaintenanceChange,
}: {
  maintenance: MaintenanceSettings
  onMaintenanceChange: (value: MaintenanceSettings) => void
}) {
  const [bundle, setBundle] = useState<BackupBundle | null>(null)
  const [sections, setSections] = useState<string[]>(
    BACKUP_SECTIONS.map(([value]) => value)
  )
  const [mode, setMode] = useState<"merge" | "overwrite">("merge")
  const [preview, setPreview] = useState<BackupPreviewResponse | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [exportPassphrase, setExportPassphrase] = useState("")
  const [importPassphrase, setImportPassphrase] = useState("")
  const [exportAdminPassword, setExportAdminPassword] = useState("")
  const [importAdminPassword, setImportAdminPassword] = useState("")
  const storage = useGetStorageStatsApiSettingsDataStorageGet()
  const exporting = useMutation<BackupBundle, ApiError>({
    mutationFn: () =>
      apiRequest<BackupBundle>("/api/settings/data/export", {
        headers: { "X-Reauth-Password": exportAdminPassword },
      }),
    onSuccess: (value) => {
      setExportAdminPassword("")
      void (async () => {
        const exported = exportPassphrase
          ? await encryptBackup(value, exportPassphrase)
          : value
        const blob = new Blob([JSON.stringify(exported, null, 2)], {
          type: "application/json",
        })
        const url = URL.createObjectURL(blob)
        const anchor = document.createElement("a")
        anchor.href = url
        anchor.download = `gpt-auto-register-${new Date().toISOString().slice(0, 10)}${exportPassphrase ? ".encrypted" : ""}.json`
        anchor.click()
        URL.revokeObjectURL(url)
        toast.success(exportPassphrase ? "加密备份已导出" : "数据备份已导出")
      })().catch((error: unknown) =>
        toast.error(error instanceof Error ? error.message : "无法加密备份")
      )
    },
    onError: (error) => toast.error(error.message),
  })
  const previewing = useMutation<BackupPreviewResponse, ApiError>({
    mutationFn: () =>
      apiRequest<BackupPreviewResponse>("/api/settings/data/preview", {
        method: "POST",
        data: { bundle, sections, mode },
      }),
    onSuccess: (value) => {
      setPreview(value)
      setConfirmed(false)
    },
    onError: (error) => toast.error(error.message),
  })
  const importing = useMutation<
    {
      added: number
      updated: number
      unchanged: number
      removed: number
      recovery_snapshot?: string | null
    },
    ApiError
  >({
    mutationFn: () =>
      apiRequest("/api/settings/data/import", {
        method: "POST",
        headers: { "X-Reauth-Password": importAdminPassword },
        data: {
          bundle,
          sections,
          mode,
          conflict_policy: "incoming",
        },
      }),
    onSuccess: (value) => {
      toast.success(
        `导入完成：新增 ${value.added}，更新 ${value.updated}，移除 ${value.removed}${value.recovery_snapshot ? `；恢复点 ${value.recovery_snapshot}` : ""}`
      )
      setBundle(null)
      setPreview(null)
      setConfirmed(false)
      setImportAdminPassword("")
    },
    onError: (error) => toast.error(error.message),
  })
  const cleanup = useMutation<
    { removed_job_events: number; removed_backup_files: number },
    ApiError
  >({
    mutationFn: () =>
      apiRequest("/api/settings/data/cleanup", { method: "POST" }),
    onSuccess: (value) => {
      toast.success(
        `已清理 ${value.removed_job_events} 条过期日志和 ${value.removed_backup_files} 个恢复点`
      )
      void storage.refetch()
    },
    onError: (error) => toast.error(error.message),
  })
  const diagnostics = useMutation<Blob, ApiError>({
    mutationFn: () =>
      apiRequest<Blob>("/api/settings/data/diagnostics", {
        responseType: "blob",
      }),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      const timestamp = new Date().toISOString().replaceAll(":", "-")
      anchor.href = url
      anchor.download = `gpt-auto-register-diagnostics-${timestamp}.zip`
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success("诊断日志包已导出")
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Section
        title="导出备份"
        description="导出系统配置、邮箱凭据、注册令牌和 Authenticator 密钥。备份文件包含敏感数据，请只保存在可信设备。"
      >
        <div className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <Field label="管理员密码（重新验证）">
            <Input
              autoComplete="current-password"
              type="password"
              value={exportAdminPassword}
              onChange={(event) => setExportAdminPassword(event.target.value)}
            />
          </Field>
          <Field label="加密口令（可选，仅在本机处理）">
            <Input
              autoComplete="new-password"
              placeholder="留空则导出普通 JSON"
              type="password"
              value={exportPassphrase}
              onChange={(event) => setExportPassphrase(event.target.value)}
            />
          </Field>
          <Button
            disabled={exporting.isPending}
            onClick={() => exporting.mutate()}
            variant="outline"
          >
            <Download />
            {exporting.isPending ? "正在导出" : "下载完整备份"}
          </Button>
        </div>
      </Section>
      <Section
        title="导入与同步"
        description="合并会保留本机额外数据；覆盖会移除所选分区中备份不存在的数据，但使用中的账号和被历史任务引用的卡密会受到保护。"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="管理员密码（重新验证）">
            <Input
              autoComplete="current-password"
              type="password"
              value={importAdminPassword}
              onChange={(event) => setImportAdminPassword(event.target.value)}
            />
          </Field>
          <Field label="解密口令（加密文件必填）">
            <Input
              autoComplete="current-password"
              type="password"
              value={importPassphrase}
              onChange={(event) => setImportPassphrase(event.target.value)}
            />
          </Field>
          <Field label="备份文件">
            <Input
              accept="application/json,.json"
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (!file) return
                void file
                  .text()
                  .then(async (text) => {
                    const parsed = JSON.parse(text) as unknown
                    const value = isEncryptedBackup(parsed)
                      ? ((await decryptBackup(
                          parsed,
                          importPassphrase
                        )) as BackupBundle)
                      : (parsed as BackupBundle)
                    if (
                      value.format !== "gpt-auto-register-backup" ||
                      value.version !== 3
                    )
                      throw new Error("不是受支持的数据备份")
                    setBundle(value)
                    setPreview(null)
                  })
                  .catch((error: unknown) =>
                    toast.error(
                      error instanceof Error
                        ? error.message
                        : "无法读取备份文件"
                    )
                  )
              }}
            />
          </Field>
          <Field label="导入模式">
            <Select
              value={mode}
              onValueChange={(value) => {
                setMode(value as "merge" | "overwrite")
                setPreview(null)
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="merge">合并</SelectItem>
                <SelectItem value="overwrite">覆盖所选分区</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {BACKUP_SECTIONS.map(([value, label]) => (
            <label className="flex items-center gap-2 text-sm" key={value}>
              <Checkbox
                checked={sections.includes(value)}
                onCheckedChange={(checked) => {
                  setSections((current) =>
                    checked
                      ? [...current, value]
                      : current.filter((item) => item !== value)
                  )
                  setPreview(null)
                }}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            disabled={!bundle || !sections.length || previewing.isPending}
            onClick={() => previewing.mutate()}
            variant="outline"
          >
            <Database />
            {previewing.isPending ? "正在分析" : "预览导入"}
          </Button>
        </div>
        {preview && (
          <div className="mt-5 border-t pt-4">
            <div className="overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="py-2">分区</th>
                    <th>新增</th>
                    <th>更新</th>
                    <th>不变</th>
                    <th>移除</th>
                    <th>保护</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(preview.sections).map(([name, value]) => (
                    <tr className="border-t" key={name}>
                      <td className="py-2">
                        {BACKUP_SECTIONS.find(([key]) => key === name)?.[1] ??
                          name}
                      </td>
                      <td>{value.added}</td>
                      <td>{value.updated}</td>
                      <td>{value.unchanged}</td>
                      <td>{value.removable}</td>
                      <td>{value.protected}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm">
              <Checkbox
                checked={confirmed}
                onCheckedChange={(value) => setConfirmed(value === true)}
              />
              我已确认以上变更并了解备份包含敏感凭据
            </label>
            <div className="mt-4 flex justify-end">
              <Button
                disabled={!confirmed || importing.isPending}
                onClick={() => importing.mutate()}
              >
                <Upload />
                {importing.isPending ? "正在导入" : "确认导入"}
              </Button>
            </div>
          </div>
        )}
      </Section>
      <Section
        title="存储与日志"
        description="按保留策略清理任务运行日志和自动恢复点；账号、凭据、卡密及业务结果不会被清理。"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="日志保留天数">
            <Input
              max={365}
              min={1}
              type="number"
              value={maintenance.job_log_retention_days}
              onChange={(event) =>
                onMaintenanceChange({
                  ...maintenance,
                  job_log_retention_days: Number(event.target.value),
                })
              }
            />
          </Field>
          <Field label="单次运行日志行数上限">
            <Input
              max={20000}
              min={100}
              type="number"
              value={maintenance.max_runtime_log_lines}
              onChange={(event) =>
                onMaintenanceChange({
                  ...maintenance,
                  max_runtime_log_lines: Number(event.target.value),
                })
              }
            />
          </Field>
          <div className="text-xs text-muted-foreground">
            <div>数据库 {formatBytes(storage.data?.database_bytes ?? 0)}</div>
            <div className="mt-1">
              日志 {storage.data?.job_events ?? 0} 条，待清理{" "}
              {storage.data?.expired_job_events ?? 0} 条
            </div>
          </div>
          <div className="text-xs text-muted-foreground">
            <div>
              恢复点 {storage.data?.backup_files ?? 0} 个，共{" "}
              {formatBytes(storage.data?.backup_bytes ?? 0)}
            </div>
            <Button
              className="mt-2"
              disabled={cleanup.isPending}
              onClick={() => cleanup.mutate()}
              size="sm"
              variant="outline"
            >
              立即清理
            </Button>
          </div>
        </div>
        <Separator className="my-4" />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="text-sm font-medium">诊断日志包</div>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
              包含最近 200 个任务、最多 20,000 条任务日志和最近 100
              个流水线摘要。文件不加密、不脱敏，日志中的邮箱、手机号、验证码、代理凭据、Cookie、密码和
              Token 会按原文保留，请只交给可信的排查人员。
            </p>
          </div>
          <Button
            className="shrink-0"
            disabled={diagnostics.isPending}
            onClick={() => diagnostics.mutate()}
            variant="outline"
          >
            <FileArchive />
            {diagnostics.isPending ? "正在打包" : "导出诊断包"}
          </Button>
        </div>
      </Section>
    </div>
  )
}
