import type { ReactNode } from "react"
import { QueryClientProvider } from "@tanstack/react-query"
import { ErrorBoundary } from "react-error-boundary"

import { AppErrorFallback } from "@/components/app-error-boundary"
import { ThemeProvider, useTheme } from "@/components/theme-provider"
import { PRODUCT_TOURS } from "@/lib/product-tours"
import { queryClient } from "@/lib/query-client"
import { Toaster } from "@workspace/ui/components/sonner"
import { TourProvider } from "@workspace/ui/components/tour"
import { TooltipProvider } from "@workspace/ui/components/tooltip"

function closeMobileSidebar() {
  if (!window.matchMedia("(max-width: 767px)").matches) return
  if (!document.querySelector('[data-sidebar="sidebar"][data-mobile="true"]'))
    return
  document.querySelector<HTMLButtonElement>('[data-sidebar="trigger"]')?.click()
}

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
      <TooltipProvider>
        <TourProvider
          tours={PRODUCT_TOURS}
          onComplete={(tourId) => {
            closeMobileSidebar()
            localStorage.setItem(
              `gpt-auto-register:tour-completed:${tourId}`,
              "1"
            )
          }}
          onSkip={closeMobileSidebar}
          onStepChange={(tourId, step) => {
            if (tourId === "quick-start" && step === 2) closeMobileSidebar()
          }}
        >
          {children}
        </TourProvider>
      </TooltipProvider>
      <Toaster theme={theme} position="top-right" richColors />
    </QueryClientProvider>
  )
}
