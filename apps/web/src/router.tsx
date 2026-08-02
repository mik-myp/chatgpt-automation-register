import { createBrowserRouter } from "react-router"

import { App } from "./App"
import { RouteError } from "./routes/route-error"

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    errorElement: <RouteError />,
    hydrateFallbackElement: (
      <div className="p-6 text-sm text-muted-foreground">正在加载...</div>
    ),
    children: [
      {
        index: true,
        lazy: () => import("./routes/dashboard"),
      },
      {
        path: "pipelines",
        lazy: () => import("./routes/pipelines"),
      },
      {
        path: "pipelines/:runId",
        lazy: () => import("./routes/pipeline-run"),
      },
      {
        path: "accounts",
        lazy: () => import("./routes/accounts"),
      },
      {
        path: "cards",
        lazy: () => import("./routes/cards"),
      },
      {
        path: "kakao",
        lazy: () => import("./routes/kakao"),
      },
      {
        path: "results",
        lazy: () => import("./routes/results"),
      },
      {
        path: "settings",
        lazy: () => import("./routes/settings"),
      },
    ],
  },
])
