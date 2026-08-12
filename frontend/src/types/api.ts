/**
 * API 通用响应类型定义
 */

/** 分页请求参数 */
export interface PaginationParams {
  page: number
  page_size: number
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  total: number
  items: T[]
}

/** 通用API响应 */
export interface ApiResponse<T = unknown> {
  detail?: string
  [key: string]: unknown
}

/** Date range query */
export interface DateRangeQuery {
  start_date: string
  end_date: string
}
