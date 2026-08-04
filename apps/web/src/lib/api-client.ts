import axios, {
  type AxiosError,
  type AxiosRequestConfig,
  type AxiosResponse,
} from "axios"

import { env } from "./env"

type ApiErrorPayload = {
  detail?: string | ApiValidationIssue[]
  message?: string
}

type ApiValidationIssue = {
  type?: string
  loc?: Array<string | number>
  msg?: string
  ctx?: { min_length?: number }
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
    if (Array.isArray(value.detail) && value.detail.length > 0) {
      const issue = value.detail[0]
      const field = String(issue.loc?.at(-1) ?? "")
      const labels: Record<string, string> = {
        token: "初始化令牌",
        username: "用户名",
        password: "密码",
        current_password: "当前密码",
        new_password: "新密码",
      }
      const label = labels[field] ?? "输入内容"
      if (issue.type === "string_too_short") {
        return `${label}至少需要 ${issue.ctx?.min_length ?? "规定"} 位`
      }
      if (issue.type === "string_pattern_mismatch") {
        return `${label}只能包含字母、数字、点、短横线和下划线`
      }
      if (issue.msg) return `${label}：${issue.msg}`
    }
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
  withCredentials: true,
  timeout: 30_000,
  headers: {
    Accept: "application/json",
  },
})

const CSRF_STORAGE_KEY = "gpt-auto-register:csrf-token"

export function setCsrfToken(value: string) {
  if (value) sessionStorage.setItem(CSRF_STORAGE_KEY, value)
  else sessionStorage.removeItem(CSRF_STORAGE_KEY)
}

apiClient.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase() ?? "GET"
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = sessionStorage.getItem(CSRF_STORAGE_KEY)
    if (csrf) config.headers.set("X-CSRF-Token", csrf)
  }
  return config
})

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      if (
        error.response?.status === 401 &&
        !String(error.config?.url ?? "").includes("/auth/login")
      ) {
        setCsrfToken("")
        if (!["/login", "/setup"].includes(window.location.pathname))
          window.location.assign("/login")
      }
      return Promise.reject(toApiError(error))
    }
    return Promise.reject(error)
  }
)

function normalizeUrl(url: string | undefined) {
  if (!url) return url
  const baseUrl = String(apiClient.defaults.baseURL ?? env.VITE_API_BASE_URL)
  let basePath = baseUrl
  try {
    basePath = new URL(baseUrl, window.location.origin).pathname
  } catch {
    // Axios will report malformed base URLs; normalization can safely skip them.
  }
  basePath = basePath.replace(/\/$/, "")
  if (basePath && basePath !== "/" && url.startsWith(`${basePath}/`)) {
    return url.slice(basePath.length)
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
