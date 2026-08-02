import { useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { Label } from "@workspace/ui/components/label"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarInput,
} from "@workspace/ui/components/sidebar"
import { SearchIcon } from "lucide-react"

export function SearchForm({ ...props }: React.ComponentProps<"form">) {
  const location = useLocation()
  const initialQuery =
    location.pathname === "/search"
      ? (new URLSearchParams(location.search).get("q") ?? "")
      : ""
  return (
    <SearchFormFields
      {...props}
      initialQuery={initialQuery}
      key={`${location.pathname}:${initialQuery}`}
    />
  )
}

function SearchFormFields({
  initialQuery,
  ...props
}: React.ComponentProps<"form"> & { initialQuery: string }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState(initialQuery)

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        const value = query.trim()
        if (value) navigate(`/search?q=${encodeURIComponent(value)}`)
      }}
      {...props}
    >
      <SidebarGroup className="py-0">
        <SidebarGroupContent className="relative">
          <Label htmlFor="search" className="sr-only">
            Search
          </Label>
          <SidebarInput
            id="search"
            placeholder="搜索账号或轮次"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="pl-8"
          />
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 opacity-50 select-none" />
        </SidebarGroupContent>
      </SidebarGroup>
    </form>
  )
}
