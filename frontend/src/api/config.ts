/**
 * 系统配置 API (只读)
 */
import request from './index'
import type { ConfigViewResponse } from '@/types/audit'

/** 获取系统配置 (只读) */
export function getConfigViewApi(): Promise<ConfigViewResponse> {
  return request.get('/config')
}
