import { createBrowserRouter } from "react-router"

import { App } from "./App"
import { AuthGate, AuthPageRoute } from "./features/auth/auth-context"
import { LoginPage } from "./features/auth/login-page"
import { SetupPage } from "./features/auth/setup-page"
import { RouteError } from "./routes/route-error"

export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <AuthPageRoute mode="login">
        <LoginPage />
      </AuthPageRoute>
    ),
  },
  {
    path: "/setup",
    element: (
      <AuthPageRoute mode="setup">
        <SetupPage />
      </AuthPageRoute>
    ),
  },
  {
    path: "/",
    element: <AuthGate />,
    errorElement: <RouteError />,
    hydrateFallbackElement: (
      <div className="p-6 text-sm text-muted-foreground">正在加载...</div>
    ),
    children: [
      {
        element: <App />,
        children: [
          { index: true, lazy: () => import("./routes/dashboard") },
          { path: "search", lazy: () => import("./routes/search") },
          { path: "pipelines", lazy: () => import("./routes/pipelines") },
          {
            path: "pipelines/:runId",
            lazy: () => import("./routes/pipeline-run"),
          },
          { path: "accounts", lazy: () => import("./routes/accounts") },
          { path: "cards", lazy: () => import("./routes/cards") },
          { path: "results", lazy: () => import("./routes/results") },
          { path: "users", lazy: () => import("./routes/users") },
          { path: "settings", lazy: () => import("./routes/settings") },
        ],
      },
    ],
  },
])
