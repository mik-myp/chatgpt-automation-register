import { createBrowserRouter } from "react-router"

import { App } from "./App"

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    hydrateFallbackElement: (
      <div className="p-6 text-sm text-muted-foreground">正在加载...</div>
    ),
    children: [
      {
        index: true,
        lazy: async () => {
          const { DashboardPage } = await import("./pages/dashboard-page")
          return { Component: DashboardPage }
        },
      },
      {
        path: "pipelines",
        lazy: async () => {
          const { PipelinesPage } = await import("./pages/pipelines-page")
          return { Component: PipelinesPage }
        },
      },
      {
        path: "pipelines/:runId",
        lazy: async () => {
          const { PipelineRunPage } = await import("./pages/pipelines-page")
          return { Component: PipelineRunPage }
        },
      },
      {
        path: "accounts",
        lazy: async () => {
          const { AccountsPage } = await import("./pages/accounts-page")
          return { Component: AccountsPage }
        },
      },
      {
        path: "cards",
        lazy: async () => {
          const { CardsPage } = await import("./pages/cards-page")
          return { Component: CardsPage }
        },
      },
      {
        path: "kakao",
        lazy: async () => {
          const { KakaoPage } = await import("./pages/kakao-page")
          return { Component: KakaoPage }
        },
      },
      {
        path: "results",
        lazy: async () => {
          const { ResultsPage } = await import("./pages/results-page")
          return { Component: ResultsPage }
        },
      },
      {
        path: "settings",
        lazy: async () => {
          const { SettingsPage } = await import("./pages/settings-page")
          return { Component: SettingsPage }
        },
      },
    ],
  },
])
