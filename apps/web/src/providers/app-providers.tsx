import type { ReactNode } from "react"
import { QueryClientProvider } from "@tanstack/react-query"
import { ErrorBoundary } from "react-error-boundary"

import { AppErrorFallback } from "@/components/app-error-boundary"
import { ThemeProvider, useTheme } from "@/components/theme-provider"
import { queryClient } from "@/lib/query-client"
import { Toaster } from "@workspace/ui/components/sonner"
import { TooltipProvider } from "@workspace/ui/components/tooltip"

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary FallbackComponent={AppErrorFallback}>
      <ThemeProvider>
        <RuntimeProviders>{children}</RuntimeProviders>
      </ThemeProvider>
    </ErrorBoundary>
  )
}

function RuntimeProviders({ children }: { children: ReactNode }) {
  const { theme } = useTheme()

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
      <Toaster theme={theme} position="top-right" richColors />
    </QueryClientProvider>
  )
}
