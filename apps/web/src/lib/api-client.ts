import axios, {
  type AxiosError,
  type AxiosRequestConfig,
  type AxiosResponse,
} from "axios"

import { env } from "./env"

type ApiErrorPayload = {
  detail?: string
  message?: string
}

export class ApiError extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(status: number, message: string, payload: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.payload = payload
  }
}

function errorMessage(status: number, payload: unknown) {
  if (typeof payload === "string" && payload) return payload
  if (payload && typeof payload === "object") {
    const value = payload as ApiErrorPayload
    if (typeof value.detail === "string" && value.detail) return value.detail
    if (typeof value.message === "string" && value.message) return value.message
  }
  if (!status) return "无法连接本地 API 服务"
  return `请求失败（${status}）`
}

function toApiError(error: AxiosError<unknown>) {
  const status = error.response?.status ?? 0
  const payload = error.response?.data
  return new ApiError(status, errorMessage(status, payload), payload)
}

export const apiClient = axios.create({
  baseURL: env.VITE_API_BASE_URL,
  timeout: 30_000,
  headers: {
    Accept: "application/json",
  },
})

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      return Promise.reject(toApiError(error))
    }
    return Promise.reject(error)
  }
)

function normalizeUrl(url: string | undefined) {
  if (!url) return url
  const baseUrl = env.VITE_API_BASE_URL.replace(/\/$/, "")
  if (baseUrl && url.startsWith(`${baseUrl}/`)) {
    return url.slice(baseUrl.length)
  }
  return url
}

export async function orvalRequest<T>(
  config: AxiosRequestConfig,
  options?: AxiosRequestConfig
): Promise<T> {
  const merged = { ...config, ...options }
  const response = await apiClient.request<T>({
    ...merged,
    url: normalizeUrl(merged.url),
  })
  return response.data
}

export function apiRequest<T>(
  path: string,
  config: AxiosRequestConfig = {}
): Promise<T> {
  return orvalRequest<T>({ ...config, url: path })
}
