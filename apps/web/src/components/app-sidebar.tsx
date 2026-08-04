import * as React from "react"
import { NavLink, useLocation } from "react-router"

import { SearchForm } from "@/components/search-form"
import { apiRequest } from "@/lib/api-client"
import { TOUR_IDS } from "@/lib/product-tours"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@workspace/ui/components/sidebar"
import {
  ClipboardCheckIcon,
  LayoutDashboardIcon,
  KeyRoundIcon,
  MailIcon,
  SettingsIcon,
  UsersIcon,
  WorkflowIcon,
} from "lucide-react"

const navigation = [
  {
    title: "运行",
    items: [
      {
        title: "工作台",
        url: "/",
        icon: LayoutDashboardIcon,
        iconColor: "text-blue-600 dark:text-blue-400",
      },
      {
        title: "流水线轮次",
        url: "/pipelines",
        icon: WorkflowIcon,
        iconColor: "text-violet-600 dark:text-violet-400",
        tourId: TOUR_IDS.navPipelines,
      },
    ],
  },
  {
    title: "资源",
    items: [
      {
        title: "邮箱号池",
        url: "/accounts",
        icon: MailIcon,
        iconColor: "text-cyan-600 dark:text-cyan-400",
        tourId: TOUR_IDS.navAccounts,
      },
      {
        title: "卡密库存",
        url: "/cards",
        icon: KeyRoundIcon,
        iconColor: "text-amber-600 dark:text-amber-400",
        tourId: TOUR_IDS.navCards,
      },
    ],
  },
  {
    title: "管理",
    items: [
      {
        title: "注册结果",
        url: "/results",
        icon: ClipboardCheckIcon,
        iconColor: "text-emerald-600 dark:text-emerald-400",
        tourId: TOUR_IDS.navResults,
      },
      {
        title: "用户管理",
        url: "/users",
        icon: UsersIcon,
        iconColor: "text-teal-600 dark:text-teal-400",
      },
      {
        title: "系统配置",
        url: "/settings",
        icon: SettingsIcon,
        iconColor: "text-neutral-600 dark:text-neutral-400",
        tourId: TOUR_IDS.navSettings,
      },
    ],
  },
]

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const [version, setVersion] = React.useState("")

  React.useEffect(() => {
    let active = true
    void apiRequest<{ version: string }>("/health")
      .then((health) => {
        if (active) setVersion(health.version)
      })
      .catch(() => {
        if (active) setVersion("不可用")
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <Sidebar {...props}>
      <nav aria-label="主导航" className="flex min-h-0 flex-1 flex-col">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton id={TOUR_IDS.appBrand} size="lg" asChild>
                <NavLink to="/">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
                    <WorkflowIcon className="size-4" />
                  </div>
                  <div className="flex min-w-0 flex-col leading-none">
                    <span className="truncate font-medium">
                      GPT Auto Register
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {version ? `v${version}` : "正在读取版本..."}
                    </span>
                  </div>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <div id={TOUR_IDS.globalSearch}>
            <SearchForm />
          </div>
        </SidebarHeader>
        <SidebarContent>
          {navigation.map((section) => (
            <SidebarGroup key={section.title}>
              <SidebarGroupLabel>{section.title}</SidebarGroupLabel>
              <SidebarMenu>
                {section.items.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton
                      asChild
                      id={item.tourId}
                      isActive={
                        location.pathname === item.url ||
                        (item.url !== "/" &&
                          location.pathname.startsWith(`${item.url}/`))
                      }
                      tooltip={item.title}
                    >
                      <NavLink to={item.url}>
                        <item.icon className={item.iconColor} />
                        <span>{item.title}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          ))}
        </SidebarContent>
      </nav>
      <SidebarRail />
    </Sidebar>
  )
}
