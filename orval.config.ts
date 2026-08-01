import { defineConfig } from "orval"

export default defineConfig({
  api: {
    input: {
      target: "http://127.0.0.1:8000/openapi.json",
    },
    output: {
      target: "apps/web/src/api/generated.ts",
      client: "react-query",
      httpClient: "axios",
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: "apps/web/src/lib/api-client.ts",
          name: "orvalRequest",
        },
      },
    },
  },
})
