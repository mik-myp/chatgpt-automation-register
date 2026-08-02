import type { ReactNode } from "react"

import {
  SettingsFormContext,
  type SettingsFormContextValue,
} from "@/features/settings/components/settings-form-state"

export function SettingsFormProvider({
  children,
  form,
  settings,
  setForm,
}: SettingsFormContextValue & { children: ReactNode }) {
  return (
    <SettingsFormContext.Provider value={{ form, settings, setForm }}>
      {children}
    </SettingsFormContext.Provider>
  )
}
