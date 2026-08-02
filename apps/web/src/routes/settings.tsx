import { getGetSettingsApiSettingsGetQueryOptions } from "@/api/generated"
import { queryClient } from "@/lib/query-client"

export async function loader() {
  await queryClient.ensureQueryData(getGetSettingsApiSettingsGetQueryOptions())
  return null
}

export { SettingsPage as Component } from "@/features/settings/pages/settings-page"
