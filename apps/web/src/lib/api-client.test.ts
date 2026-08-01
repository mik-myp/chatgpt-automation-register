import MockAdapter from "axios-mock-adapter"
import { afterEach, describe, expect, it } from "vitest"

import { apiClient, apiRequest } from "./api-client"

const mock = new MockAdapter(apiClient)

afterEach(() => {
  mock.reset()
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
})
