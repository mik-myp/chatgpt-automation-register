import { Outlet } from "react-router"

import { ApiStatus } from "@/components/api-status"
import { AppSidebar } from "@/components/app-sidebar"

import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@workspace/ui/components/sidebar"

export function App() {
  return (
    <SidebarProvider className="h-svh min-h-0 overflow-hidden">
      <AppSidebar />
      <SidebarInset className="h-svh min-h-0 overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <ApiStatus />
        </header>
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden p-4 md:p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export function WorkspacePage({ title }: { title: string }) {
  return <h1 className="text-xl font-semibold">{title}</h1>
}
