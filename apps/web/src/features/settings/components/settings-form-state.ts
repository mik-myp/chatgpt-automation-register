import { createContext, useContext } from "react"

import type {
  SystemSettingsResponse,
  SystemSettingsUpdate,
} from "@/api/generated"

export type SettingsFormContextValue = {
  form: SystemSettingsUpdate
  settings: { data?: SystemSettingsResponse }
  setForm: (form: SystemSettingsUpdate) => void
}

export const SettingsFormContext =
  createContext<SettingsFormContextValue | null>(null)

export function useSettingsForm() {
  const context = useContext(SettingsFormContext)
  if (!context) throw new Error("Settings tabs require SettingsFormProvider")
  return context
}
