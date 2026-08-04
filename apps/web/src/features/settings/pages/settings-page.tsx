import { useState } from "react"
import { Save } from "lucide-react"
import { toast } from "sonner"

import {
  type SystemSettingsResponse,
  type SystemSettingsUpdate,
  useGetSettingsApiSettingsGet,
  useUpdateSettingsApiSettingsPut,
} from "@/api/generated"
import { DataTransferPanel } from "@/components/settings/data-transfer-panel"
import { DeliveryCopyPanel } from "@/components/settings/delivery-copy-panel"
import { ExportSettingsTab } from "@/features/settings/components/export-settings-tab"
import { KakaoSettingsTab } from "@/features/settings/components/kakao-settings-tab"
import { MailSettingsTab } from "@/features/settings/components/mail-settings-tab"
import { RegistrationSettingsTab } from "@/features/settings/components/registration-settings-tab"
import { PipelineSettingsTab } from "@/features/settings/components/pipeline-settings-tab"
import { SettingsFormProvider } from "@/features/settings/components/settings-form-context"
import { SmsSettingsTab } from "@/features/settings/components/sms-settings-tab"
import { ApiError } from "@/lib/api-client"
import { TOUR_IDS } from "@/lib/product-tours"
import { Button } from "@workspace/ui/components/button"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@workspace/ui/components/tabs"
function editableSettings(
  settings: SystemSettingsResponse | undefined
): SystemSettingsUpdate | null {
  if (!settings) return null
  return {
    registration: { ...settings.registration },
    proxy: { ...settings.proxy },
    pipeline: {
      ...settings.pipeline,
      step_order: [...(settings.pipeline.step_order ?? [])],
    },
    mail: {
      source: settings.mail.source,
      cf_api_url: settings.mail.cf_api_url,
      cf_domain: settings.mail.cf_domain,
      cf_admin_token: "",
    },
    kakao: { ...settings.kakao },
    sms: {
      enabled: settings.sms.enabled,
      provider: settings.sms.provider,
      country: settings.sms.country,
      service: settings.sms.service,
      max_price: settings.sms.max_price,
      reuse_phone: settings.sms.reuse_phone,
      phone_success_max: settings.sms.phone_success_max,
      auto_country: settings.sms.auto_country,
      strict_whitelist: settings.sms.strict_whitelist,
      allowed_countries: settings.sms.allowed_countries,
      auto_min_stock: settings.sms.auto_min_stock,
      auto_max_price: settings.sms.auto_max_price,
      max_phone_attempts: settings.sms.max_phone_attempts,
      per_phone_timeout: settings.sms.per_phone_timeout,
      api_key: "",
    },
    export: {
      cpa: {
        enabled: settings.export.cpa?.enabled,
        url: settings.export.cpa?.url,
        timeout: settings.export.cpa?.timeout,
        key: "",
      },
      sub2api: {
        enabled: settings.export.sub2api?.enabled,
        url: settings.export.sub2api?.url,
        timeout: settings.export.sub2api?.timeout,
        key: "",
      },
      sub2api_group_ids: settings.export.sub2api_group_ids,
    },
    delivery_copy: {
      only_copy_plus: settings.delivery_copy.only_copy_plus ?? false,
      payment_links: {
        ...settings.delivery_copy.payment_links,
        rows: settings.delivery_copy.payment_links?.rows?.map((row) => ({
          ...row,
          fields: [...row.fields],
        })),
      },
      mail_access: {
        ...settings.delivery_copy.mail_access,
        rows: settings.delivery_copy.mail_access?.rows?.map((row) => ({
          ...row,
          fields: [...row.fields],
        })),
      },
      security_credentials: {
        ...settings.delivery_copy.security_credentials,
        rows: settings.delivery_copy.security_credentials?.rows?.map((row) => ({
          ...row,
          fields: [...row.fields],
        })),
      },
    },
    maintenance: { ...settings.maintenance },
  }
}

export function SettingsPage() {
  const settings = useGetSettingsApiSettingsGet()
  const [draft, setForm] = useState<SystemSettingsUpdate | null>(null)
  const form = draft ?? editableSettings(settings.data)

  const mutation = useUpdateSettingsApiSettingsPut<ApiError>({
    mutation: {
      onSuccess: () => {
        toast.success("系统配置已保存")
        setForm((current) =>
          current
            ? {
                ...current,
                mail: { ...current.mail, cf_admin_token: "" },
                sms: { ...current.sms, api_key: "" },
                export: {
                  ...current.export,
                  cpa: { ...current.export.cpa, key: "" },
                  sub2api: { ...current.export.sub2api, key: "" },
                },
              }
            : current
        )
        void settings.refetch()
      },
      onError: (error) => toast.error(error.message),
    },
  })

  if (!form)
    return <div className="text-sm text-muted-foreground">正在读取配置...</div>

  return (
    <div className="flex h-full min-h-0 flex-col gap-5">
      <div
        className="flex items-center justify-between"
        id={TOUR_IDS.settingsHeader}
      >
        <h1 className="text-xl font-semibold">系统配置</h1>
        <Button
          disabled={mutation.isPending}
          id={TOUR_IDS.settingsSave}
          onClick={() => mutation.mutate({ data: form })}
        >
          <Save />
          {mutation.isPending ? "正在保存" : "保存配置"}
        </Button>
      </div>

      <SettingsFormProvider
        form={form}
        settings={{ data: settings.data }}
        setForm={setForm}
      >
        <Tabs
          className="flex min-h-0 flex-1 flex-col"
          defaultValue="registration"
        >
          <TabsList
            className="w-full shrink-0 justify-start"
            id={TOUR_IDS.settingsTabs}
          >
            <TabsTrigger className="shrink-0" value="registration">
              注册
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="pipeline">
              流水线与代理
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="mail">
              邮箱
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="kakao">
              Kakao
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="sms">
              接码
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="export">
              自动导出
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="delivery">
              交付复制
            </TabsTrigger>
            <TabsTrigger className="shrink-0" value="data">
              数据同步
            </TabsTrigger>
          </TabsList>

          <div className="flex min-h-0 flex-1 flex-col">
            <RegistrationSettingsTab />
            <PipelineSettingsTab />
            <MailSettingsTab />
            <KakaoSettingsTab />
            <SmsSettingsTab />
            <ExportSettingsTab />
            <TabsContent
              className="mt-5 min-h-0 flex-1 overflow-auto"
              value="delivery"
            >
              <DeliveryCopyPanel
                value={form.delivery_copy}
                onChange={(delivery_copy) =>
                  setForm({ ...form, delivery_copy })
                }
              />
            </TabsContent>
            <TabsContent
              className="mt-5 min-h-0 flex-1 overflow-auto"
              value="data"
            >
              <DataTransferPanel
                maintenance={
                  form.maintenance ?? {
                    job_log_retention_days: 14,
                    max_runtime_log_lines: 2000,
                  }
                }
                onMaintenanceChange={(maintenance) =>
                  setForm({ ...form, maintenance })
                }
              />
            </TabsContent>
          </div>
        </Tabs>
      </SettingsFormProvider>
    </div>
  )
}
