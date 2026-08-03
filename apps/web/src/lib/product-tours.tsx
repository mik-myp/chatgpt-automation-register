/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from "react"

import type { TourDefinition } from "@workspace/ui/components/tour"

export const TOUR_IDS = {
  appBrand: "tour-app-brand",
  globalSearch: "tour-global-search",
  navPipelines: "tour-nav-pipelines",
  navAccounts: "tour-nav-accounts",
  navCards: "tour-nav-cards",
  navResults: "tour-nav-results",
  navSettings: "tour-nav-settings",
  tourMenu: "tour-menu",
  dashboardOverview: "tour-dashboard-overview",
  dashboardRecent: "tour-dashboard-recent",
  dashboardResources: "tour-dashboard-resources",
  pipelinesHeader: "tour-pipelines-header",
  pipelineActions: "tour-pipeline-actions",
  createRegistration: "tour-create-registration",
  pipelineList: "tour-pipeline-list",
  accountsHeader: "tour-accounts-header",
  accountsImport: "tour-accounts-import",
  accountsStatus: "tour-accounts-status",
  accountsList: "tour-accounts-list",
  resultsHeader: "tour-results-header",
  resultsActions: "tour-results-actions",
  resultsList: "tour-results-list",
  settingsHeader: "tour-settings-header",
  settingsSave: "tour-settings-save",
  settingsTabs: "tour-settings-tabs",
} as const

export type ProductTourId =
  | "quick-start"
  | "registration"
  | "resources"
  | "results"
  | "settings"

export interface ProductTourMeta {
  id: ProductTourId
  label: string
  description: string
  route: string
  firstSelectorId: string
}

function StepContent({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1 pr-8">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="text-sm leading-6 text-muted-foreground">{children}</p>
    </div>
  )
}

export const PRODUCT_TOUR_META: ProductTourMeta[] = [
  {
    id: "quick-start",
    label: "快速开始",
    description: "认识导航、运行概览与主要工作区",
    route: "/",
    firstSelectorId: TOUR_IDS.appBrand,
  },
  {
    id: "registration",
    label: "注册流水线",
    description: "创建注册任务并查看执行进度",
    route: "/pipelines",
    firstSelectorId: TOUR_IDS.pipelinesHeader,
  },
  {
    id: "resources",
    label: "资源准备",
    description: "导入邮箱并理解号池状态",
    route: "/accounts",
    firstSelectorId: TOUR_IDS.accountsHeader,
  },
  {
    id: "results",
    label: "结果交付",
    description: "检查、发布与导出注册结果",
    route: "/results",
    firstSelectorId: TOUR_IDS.resultsHeader,
  },
  {
    id: "settings",
    label: "系统配置",
    description: "完成注册运行前的必要配置",
    route: "/settings",
    firstSelectorId: TOUR_IDS.settingsHeader,
  },
]

export const PRODUCT_TOURS: TourDefinition[] = [
  {
    id: "quick-start",
    steps: [
      {
        selectorId: TOUR_IDS.appBrand,
        position: "right",
        content: (
          <StepContent title="本地注册控制台">
            所有账号、卡密和凭证都在本机处理。左侧导航按运行、资源和管理三个阶段组织。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.globalSearch,
        position: "right",
        content: (
          <StepContent title="全局查找">
            输入邮箱或轮次编号，可以快速定位账号、流水线和注册结果。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.dashboardOverview,
        position: "bottom",
        content: (
          <StepContent title="先确认运行状态">
            开始前检查可用邮箱、启用卡密、执行中任务和需要处理的异常数量。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.dashboardRecent,
        position: "right",
        content: (
          <StepContent title="跟进最近轮次">
            流水线创建后会出现在这里。进入详情可查看每个账号、Kakao
            任务和运行日志。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.dashboardResources,
        position: "left",
        content: (
          <StepContent title="资源决定可执行容量">
            邮箱负责注册，卡密用于 Kakao
            任务。库存不足时，相应创建操作会被禁用。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.tourMenu,
        position: "bottom",
        content: (
          <StepContent title="随时重新查看">
            从这里启动注册、资源、结果或配置的专项导览。
          </StepContent>
        ),
      },
    ],
  },
  {
    id: "registration",
    steps: [
      {
        selectorId: TOUR_IDS.pipelinesHeader,
        content: (
          <StepContent title="流水线是执行单位">
            每个轮次保存当时的配置快照，并独立记录目标数、成功数、失败数与状态。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.pipelineActions,
        position: "bottom",
        content: (
          <StepContent title="三类任务入口">
            新建注册负责生成账号；安全处理负责密码与 MFA；Kakao
            使用已有成功凭证创建任务。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.createRegistration,
        position: "bottom",
        content: (
          <StepContent title="从注册开始">
            选择单次或批量模式，设置目标数量、并发和代理。启用 Kakao
            时还需足够卡密容量。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.pipelineList,
        position: "top",
        content: (
          <StepContent title="进入轮次查看细节">
            轮次详情包含注册项、Kakao 任务、交付信息、卡密分配和实时运行日志。
          </StepContent>
        ),
      },
    ],
  },
  {
    id: "resources",
    steps: [
      {
        selectorId: TOUR_IDS.accountsHeader,
        content: (
          <StepContent title="先准备邮箱号池">
            注册任务会从可用账号中领取邮箱，并在成功或失败后更新账号状态。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.accountsImport,
        position: "bottom",
        content: (
          <StepContent title="批量导入邮箱">
            导入前确认邮箱格式、收信方式和凭证完整，重复邮箱会按导入规则处理。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.accountsStatus,
        position: "bottom",
        content: (
          <StepContent title="关注可用与失败数量">
            可用账号决定注册容量；失败账号可批量重试，卡死账号可通过维护操作释放。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.accountsList,
        position: "top",
        content: (
          <StepContent title="按状态筛选和处理">
            表格会显示注册状态、密码、MFA、领取时间和最近错误。需要 Kakao
            时，再到卡密库存导入卡密并检查实时用量。
          </StepContent>
        ),
      },
    ],
  },
  {
    id: "results",
    steps: [
      {
        selectorId: TOUR_IDS.resultsHeader,
        content: (
          <StepContent title="注册凭证集中在这里">
            注册成功后保存密码、MFA
            和各类令牌，后续检查与发布都以这些结果为基础。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.resultsActions,
        position: "bottom",
        content: (
          <StepContent title="批量检查与交付">
            先严格检查 Plus，再按需要发布到 CPA 或 SUB2API；也可以导出本地备份。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.resultsList,
        position: "top",
        content: (
          <StepContent title="核对每条凭证">
            使用筛选和详情查看令牌完整性、Plus
            状态与保存时间，再决定发布或删除。
          </StepContent>
        ),
      },
    ],
  },
  {
    id: "settings",
    steps: [
      {
        selectorId: TOUR_IDS.settingsHeader,
        content: (
          <StepContent title="配置会影响后续新任务">
            流水线创建时会保存配置快照，因此修改配置不会改变已经创建的轮次。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.settingsTabs,
        position: "bottom",
        content: (
          <StepContent title="按依赖顺序配置">
            建议依次完成注册、邮箱、Kakao、接码和自动导出，再设置交付复制与数据同步。邮箱、接码、Kakao
            和导出目标保存前都应先测试连接。
          </StepContent>
        ),
      },
      {
        selectorId: TOUR_IDS.settingsSave,
        position: "bottom",
        content: (
          <StepContent title="最后保存配置">
            修改只保存在当前表单中，点击保存后才会应用到之后创建的任务。
          </StepContent>
        ),
      },
    ],
  },
]
