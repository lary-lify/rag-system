/**
 * 审计日志 & 系统配置 类型
 */

import type { PaginatedResponse } from './api'

/** 审计日志 */
export interface AuditLogInfo {
  id: number
  user_id: number | null
  username: string
  action: string
  resource_type: string
  resource_id: number | null
  detail: Record<string, unknown>
  ip_address: string
  user_agent: string
  created_at: string
}

/** 审计日志列表响应 */
export type AuditLogListResponse = PaginatedResponse<AuditLogInfo>

/** 审计日志筛选 */
export interface AuditFilterParams {
  page: number
  page_size: number
  action?: string
  resource_type?: string
  user_id?: number
  start_date?: string
  end_date?: string
}

/** 配置项 */
export interface ConfigItem {
  key: string
  value: string
  description: string
}

/** 系统配置响应 */
export interface ConfigViewResponse {
  config_items: ConfigItem[]
}
