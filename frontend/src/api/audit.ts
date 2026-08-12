/**
 * 审计日志 API
 */
import request from './index'
import type { AuditLogInfo, AuditLogListResponse, AuditFilterParams } from '@/types/audit'

/** 审计日志列表 */
export function listAuditLogsApi(params: AuditFilterParams): Promise<AuditLogListResponse> {
  return request.get('/audit', { params })
}

/** 导出审计日志 CSV (返回 Blob) */
export function exportAuditLogsApi(params: {
  action?: string
  resource_type?: string
}): Promise<Blob> {
  return request.get('/audit/export', {
    params,
    responseType: 'blob',
  })
}
