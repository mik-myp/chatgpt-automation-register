import { type ReactNode } from "react"
import { ChevronLeft, ChevronRight, Trash2 } from "lucide-react"

import {
  type DeliveryCopyRowFieldsItem,
  type DeliveryCopySettings,
  type DeliveryFormatSettings,
} from "@/api/generated"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@workspace/ui/components/select"
import { Switch } from "@workspace/ui/components/switch"

const PAYMENT_DEFAULT: DeliveryFormatSettings = {
  sequence_style: "chinese",
  record_separator: "blank_line",
  show_labels: false,
  missing_policy: "skip",
  placeholder: "-",
  rows: [{ fields: ["payment_url"], separator: "" }],
}

const MAIL_ACCESS_DEFAULT: DeliveryFormatSettings = {
  sequence_style: "none",
  record_separator: "blank_line",
  show_labels: false,
  missing_policy: "skip",
  placeholder: "-",
  rows: [
    {
      fields: ["email", "mail_url"],
      separator: " --- ",
    },
  ],
}

const SECURITY_CREDENTIALS_DEFAULT: DeliveryFormatSettings = {
  sequence_style: "none",
  record_separator: "blank_line",
  show_labels: false,
  missing_policy: "skip",
  placeholder: "-",
  rows: [
    {
      fields: ["email", "chatgpt_password", "totp_secret"],
      separator: " --- ",
    },
  ],
}

const ACCOUNT_FIELDS: Array<{
  value: DeliveryCopyRowFieldsItem
  label: string
  sample: string
}> = [
  { value: "email", label: "邮箱", sample: "user@example.com" },
  {
    value: "mail_url",
    label: "邮件查询地址",
    sample: "https://mail.example.com/inbox",
  },
  { value: "chatgpt_password", label: "ChatGPT 密码", sample: "Password123" },
  {
    value: "totp_secret",
    label: "Authenticator 密钥",
    sample: "JBSWY3DPEHPK3PXP",
  },
]

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
  description: string
  children: ReactNode
}) {
  return (
    <section className="border-t py-5 first:border-t-0 first:pt-0 last:border-b">
      <h2 className="mb-1 text-sm font-semibold">{title}</h2>
      <p className="mb-4 max-w-3xl text-xs leading-5 text-muted-foreground">
        {description}
      </p>
      {children}
    </section>
  )
}

function FormatControls({
  value,
  onChange,
  account,
}: {
  value: DeliveryFormatSettings
  onChange: (value: DeliveryFormatSettings) => void
  account: boolean
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Field label="序号格式">
        <Select
          value={value.sequence_style ?? "none"}
          onValueChange={(sequence_style) =>
            onChange({
              ...value,
              sequence_style:
                sequence_style as DeliveryFormatSettings["sequence_style"],
            })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">不显示序号</SelectItem>
            <SelectItem value="number">1.</SelectItem>
            <SelectItem value="chinese_number">第1个</SelectItem>
            <SelectItem value="chinese">第一个</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <Field label="记录间隔">
        <Select
          value={value.record_separator ?? "blank_line"}
          onValueChange={(record_separator) =>
            onChange({
              ...value,
              record_separator:
                record_separator as DeliveryFormatSettings["record_separator"],
            })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="newline">换行</SelectItem>
            <SelectItem value="blank_line">空一行</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      {account && (
        <Field label="缺失字段处理">
          <Select
            value={value.missing_policy ?? "placeholder"}
            onValueChange={(missing_policy) =>
              onChange({
                ...value,
                missing_policy:
                  missing_policy as DeliveryFormatSettings["missing_policy"],
              })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="placeholder">保留占位符</SelectItem>
              <SelectItem value="skip">跳过整条记录</SelectItem>
            </SelectContent>
          </Select>
        </Field>
      )}
      {account && (
        <Field label="占位符">
          <Input
            disabled={value.missing_policy === "skip"}
            maxLength={16}
            value={value.placeholder ?? "-"}
            onChange={(event) =>
              onChange({ ...value, placeholder: event.target.value })
            }
          />
        </Field>
      )}
      <label className="flex min-h-9 items-center justify-between gap-3 text-sm">
        显示字段名称
        <Switch
          checked={value.show_labels ?? false}
          onCheckedChange={(show_labels) => onChange({ ...value, show_labels })}
        />
      </label>
    </div>
  )
}

function preview(value: DeliveryFormatSettings, payment: boolean) {
  const samples: Record<string, string> = Object.fromEntries(
    ACCOUNT_FIELDS.map((field) => [field.value, field.sample])
  )
  samples.payment_url = "https://pay.example.com/checkout"
  const lines = (value.rows ?? []).map((row) =>
    row.fields
      .map((field) => {
        const sample = samples[field]
        const label = payment
          ? "支付链接"
          : ACCOUNT_FIELDS.find((item) => item.value === field)?.label
        return value.show_labels ? `${label}: ${sample}` : sample
      })
      .join(row.separator ?? " --- ")
  )
  const prefix = {
    none: "",
    number: "1.",
    chinese_number: "第1个",
    chinese: "第一个",
  }[value.sequence_style ?? "none"]
  return [prefix, ...lines].filter(Boolean).join("\n")
}

function AccountRows({
  value,
  onChange,
  fields,
  defaultValue,
}: {
  value: DeliveryFormatSettings
  onChange: (value: DeliveryFormatSettings) => void
  fields: typeof ACCOUNT_FIELDS
  defaultValue: DeliveryFormatSettings
}) {
  const rows = value.rows ?? defaultValue.rows ?? []
  const setRows = (next: typeof rows) => onChange({ ...value, rows: next })
  return (
    <div className="mt-5 grid gap-3">
      {rows.map((row, rowIndex) => (
        <div className="border p-3" key={rowIndex}>
          <div className="mb-3 flex items-center gap-2">
            <span className="text-xs font-medium">第 {rowIndex + 1} 行</span>
            <Input
              aria-label={`第 ${rowIndex + 1} 行分隔符`}
              className="ml-auto w-28 font-mono"
              maxLength={32}
              value={row.separator ?? " --- "}
              onChange={(event) => {
                const next = [...rows]
                next[rowIndex] = { ...row, separator: event.target.value }
                setRows(next)
              }}
            />
            <Button
              aria-label={`删除第 ${rowIndex + 1} 行`}
              disabled={rows.length <= 1}
              onClick={() =>
                setRows(rows.filter((_, index) => index !== rowIndex))
              }
              size="icon-sm"
              variant="ghost"
            >
              <Trash2 />
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {row.fields.map((field, fieldIndex) => {
              const label =
                fields.find((item) => item.value === field)?.label ?? field
              const move = (offset: number) => {
                const fields = [...row.fields]
                const target = fieldIndex + offset
                ;[fields[fieldIndex], fields[target]] = [
                  fields[target],
                  fields[fieldIndex],
                ]
                const next = [...rows]
                next[rowIndex] = { ...row, fields }
                setRows(next)
              }
              return (
                <div
                  className="flex items-center border bg-muted/20"
                  key={`${field}-${fieldIndex}`}
                >
                  <span className="px-2 text-xs">{label}</span>
                  <Button
                    aria-label={`${label}向前移动`}
                    disabled={fieldIndex === 0}
                    onClick={() => move(-1)}
                    size="icon-sm"
                    variant="ghost"
                  >
                    <ChevronLeft />
                  </Button>
                  <Button
                    aria-label={`${label}向后移动`}
                    disabled={fieldIndex === row.fields.length - 1}
                    onClick={() => move(1)}
                    size="icon-sm"
                    variant="ghost"
                  >
                    <ChevronRight />
                  </Button>
                  <Button
                    aria-label={`移除${label}`}
                    disabled={row.fields.length <= 1}
                    onClick={() => {
                      const next = [...rows]
                      next[rowIndex] = {
                        ...row,
                        fields: row.fields.filter(
                          (_, index) => index !== fieldIndex
                        ),
                      }
                      setRows(next)
                    }}
                    size="icon-sm"
                    variant="ghost"
                  >
                    <Trash2 />
                  </Button>
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {fields
              .filter((field) => !row.fields.includes(field.value))
              .map((field) => (
                <Button
                  key={field.value}
                  onClick={() => {
                    const next = [...rows]
                    next[rowIndex] = {
                      ...row,
                      fields: [...row.fields, field.value],
                    }
                    setRows(next)
                  }}
                  size="sm"
                  variant="outline"
                >
                  + {field.label}
                </Button>
              ))}
          </div>
        </div>
      ))}
      <Button
        className="w-fit"
        disabled={rows.length >= 10}
        onClick={() =>
          setRows([...rows, { fields: ["email"], separator: " --- " }])
        }
        size="sm"
        variant="outline"
      >
        新增一行
      </Button>
    </div>
  )
}

export function DeliveryCopyPanel({
  value,
  onChange,
}: {
  value: DeliveryCopySettings
  onChange: (value: DeliveryCopySettings) => void
}) {
  const payment = value.payment_links ?? PAYMENT_DEFAULT
  const mailAccess = value.mail_access ?? MAIL_ACCESS_DEFAULT
  const securityCredentials =
    value.security_credentials ?? SECURITY_CREDENTIALS_DEFAULT
  const mailFields = ACCOUNT_FIELDS.filter((field) =>
    ["email", "mail_url"].includes(field.value)
  )
  const securityFields = ACCOUNT_FIELDS.filter((field) =>
    ["email", "chatgpt_password", "totp_secret"].includes(field.value)
  )
  return (
    <div className="mx-auto w-full max-w-5xl">
      <Section
        title="Plus 交付限制"
        description="开启后，复制邮箱信息或安全凭证时只保留经过严格检查且确认有效的 Plus 邮箱；支付链接复制不受影响。"
      >
        <label className="flex max-w-2xl items-center justify-between gap-4 text-sm">
          <span>仅复制确认是 Plus 的邮箱</span>
          <Switch
            checked={value.only_copy_plus ?? false}
            onCheckedChange={(only_copy_plus) =>
              onChange({ ...value, only_copy_plus })
            }
          />
        </label>
      </Section>
      <Section
        title="支付链接复制"
        description="只复制成功提取的 Kakao 支付链接，使用独立的序号和记录间隔。"
      >
        <FormatControls
          account={false}
          value={payment}
          onChange={(payment_links) => onChange({ ...value, payment_links })}
        />
        <pre className="mt-5 overflow-auto border bg-muted/20 p-4 font-mono text-xs whitespace-pre-wrap">
          {preview(payment, true)}
        </pre>
      </Section>
      <Section
        title="邮箱访问格式"
        description="密码或 MFA 尚未完成时使用，固定包含邮箱和邮件查询地址；缺少邮件查询地址的账号会跳过。"
      >
        <FormatControls
          account={false}
          value={mailAccess}
          onChange={(mail_access) => onChange({ ...value, mail_access })}
        />
        <AccountRows
          value={mailAccess}
          fields={mailFields}
          defaultValue={MAIL_ACCESS_DEFAULT}
          onChange={(mail_access) => onChange({ ...value, mail_access })}
        />
        <pre className="mt-5 overflow-auto border bg-muted/20 p-4 font-mono text-xs whitespace-pre-wrap">
          {preview(mailAccess, false)}
        </pre>
      </Section>
      <Section
        title="安全凭证格式"
        description="只有密码和 MFA 均由服务端确认成功时使用，固定包含邮箱、ChatGPT 密码和 Authenticator 密钥。"
      >
        <FormatControls
          account={false}
          value={securityCredentials}
          onChange={(security_credentials) =>
            onChange({ ...value, security_credentials })
          }
        />
        <AccountRows
          value={securityCredentials}
          fields={securityFields}
          defaultValue={SECURITY_CREDENTIALS_DEFAULT}
          onChange={(security_credentials) =>
            onChange({ ...value, security_credentials })
          }
        />
        <pre className="mt-5 overflow-auto border bg-muted/20 p-4 font-mono text-xs whitespace-pre-wrap">
          {preview(securityCredentials, false)}
        </pre>
      </Section>
    </div>
  )
}
