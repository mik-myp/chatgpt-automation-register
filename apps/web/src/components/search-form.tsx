"use client"

import { useWorkspaceStore } from "@/stores/workspace-store"
import { Label } from "@workspace/ui/components/label"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarInput,
} from "@workspace/ui/components/sidebar"
import { SearchIcon } from "lucide-react"

export function SearchForm({ ...props }: React.ComponentProps<"form">) {
  const searchQuery = useWorkspaceStore((state) => state.searchQuery)
  const setSearchQuery = useWorkspaceStore((state) => state.setSearchQuery)

  return (
    <form onSubmit={(event) => event.preventDefault()} {...props}>
      <SidebarGroup className="py-0">
        <SidebarGroupContent className="relative">
          <Label htmlFor="search" className="sr-only">
            Search
          </Label>
          <SidebarInput
            id="search"
            placeholder="搜索账号或轮次"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="pl-8"
          />
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 opacity-50 select-none" />
        </SidebarGroupContent>
      </SidebarGroup>
    </form>
  )
}
