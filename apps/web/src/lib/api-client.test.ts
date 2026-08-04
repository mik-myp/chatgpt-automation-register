import MockAdapter from "axios-mock-adapter"
import { afterEach, describe, expect, it } from "vitest"

import { apiClient, apiRequest, orvalRequest } from "./api-client"

const mock = new MockAdapter(apiClient)
const defaultBaseUrl = apiClient.defaults.baseURL

afterEach(() => {
  mock.reset()
  apiClient.defaults.baseURL = defaultBaseUrl
})

describe("apiRequest", () => {
  it("returns a JSON response", async () => {
    mock.onGet("/health").reply(200, { ok: true })

    await expect(apiRequest<{ ok: boolean }>("/health")).resolves.toEqual({
      ok: true,
    })
  })

  it("exposes the backend error detail", async () => {
    mock.onGet("/pipeline-runs").reply(409, { detail: "号池为空" })

    await expect(apiRequest("/pipeline-runs")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "号池为空",
    })
  })

  it("normalizes generated API paths with an absolute base URL", async () => {
    apiClient.defaults.baseURL = "https://register.example.com/api"
    mock.onGet("/health").reply(200, { ok: true })

    await expect(
      orvalRequest<{ ok: boolean }>({ url: "/api/health", method: "GET" })
    ).resolves.toEqual({ ok: true })
  })

  it("turns validation details into actionable messages", async () => {
    mock.onPost("/setup/initialize").reply(422, {
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "password"],
          msg: "String should have at least 6 characters",
          ctx: { min_length: 6 },
        },
      ],
    })

    await expect(
      apiRequest("/setup/initialize", { method: "POST" })
    ).rejects.toMatchObject({
      status: 422,
      message: "密码至少需要 6 位",
    })
  })
})
