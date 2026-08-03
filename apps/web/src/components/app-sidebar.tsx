import * as React from "react"
import { NavLink, useLocation } from "react-router"

import { SearchForm } from "@/components/search-form"
import { TOUR_IDS } from "@/lib/product-tours"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
} from "@workspace/ui/components/sidebar"
import {
  BoxesIcon,
  ChevronDownIcon,
  KeyRoundIcon,
  MailIcon,
  SettingsIcon,
  WorkflowIcon,
} from "lucide-react"

const navigation = [
  {
    title: "运行",
    items: [
      { title: "工作台", url: "/", icon: BoxesIcon },
      {
        title: "流水线轮次",
        url: "/pipelines",
        icon: WorkflowIcon,
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
        tourId: TOUR_IDS.navAccounts,
      },
      {
        title: "卡密库存",
        url: "/cards",
        icon: KeyRoundIcon,
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
        icon: BoxesIcon,
        tourId: TOUR_IDS.navResults,
      },
      {
        title: "系统配置",
        url: "/settings",
        icon: SettingsIcon,
        tourId: TOUR_IDS.navSettings,
      },
    ],
  },
]

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()

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
                      控制台
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
              <SidebarMenu>
                <Collapsible asChild className="group/collapsible" defaultOpen>
                  <SidebarMenuItem>
                    <CollapsibleTrigger asChild>
                      <SidebarMenuButton>
                        {section.title}
                        <ChevronDownIcon className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-180" />
                      </SidebarMenuButton>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <SidebarMenuSub>
                        {section.items.map((item) => (
                          <SidebarMenuSubItem key={item.url}>
                            <SidebarMenuSubButton
                              asChild
                              id={item.tourId}
                              isActive={location.pathname === item.url}
                            >
                              <NavLink to={item.url}>
                                <item.icon />
                                <span>{item.title}</span>
                              </NavLink>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        ))}
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  </SidebarMenuItem>
                </Collapsible>
              </SidebarMenu>
            </SidebarGroup>
          ))}
        </SidebarContent>
      </nav>
      <SidebarRail />
    </Sidebar>
  )
}
