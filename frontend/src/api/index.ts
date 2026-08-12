/**
 * Axios 实例封装 — 统一请求拦截、响应拦截、错误处理
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { message } from 'ant-design-vue'

/** 创建 axios 实例 */
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 请求拦截器 — 自动附加 JWT Token */
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

/** 响应拦截器 — 统一错误处理 */
request.interceptors.response.use(
  (response) => {
    // 直接返回 data，简化调用方取 res.data
    return response.data
  },
  (error: AxiosError) => {
    const status = error.response?.status
    const data = error.response?.data as any
    // FastAPI 422 validation error: detail is array of {loc, msg, type}
    // FastAPI other errors: detail is string
    let detail: string | undefined
    if (typeof data?.detail === 'string') {
      detail = data.detail
    } else if (Array.isArray(data?.detail)) {
      // Extract first validation error message
      detail = data.detail.map((e: any) => e.msg || JSON.stringify(e)).join('; ')
    } else if (data?.detail) {
      detail = String(data.detail)
    }

    switch (status) {
      case 401:
        // Token 过期，清除登录态，跳转登录页
        localStorage.removeItem('access_token')
        localStorage.removeItem('user_info')
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        message.error('登录已过期，请重新登录')
        break
      case 403:
        message.error(detail || '权限不足')
        break
      case 404:
        message.error(detail || '请求的资源不存在')
        break
      case 413:
        message.error('文件过大，请检查上传限制')
        break
      case 422:
        // 静默处理 — 通常是参数校验，不弹窗打扰用户
        console.warn('[API Validation]', detail)
        break
      case 500:
        message.error('服务器内部错误，请稍后重试')
        break
      default:
        if (detail && status) {
          message.error(detail)
        }
        // 网络错误等无响应的情况不弹窗（避免刷新页面的干扰）
    }

    return Promise.reject(error)
  }
)

export default request
