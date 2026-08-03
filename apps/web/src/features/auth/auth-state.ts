import { createContext, useContext } from "react"

export type AuthSession = {
  username: string
  role: string
  csrf_token: string
}

export type AuthContextValue = {
  session: AuthSession
  clearSession: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error("useAuth must be used inside AuthGate")
  return value
}
