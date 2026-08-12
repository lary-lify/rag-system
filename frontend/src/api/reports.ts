/**
 * 报表 & 费用统计 API
 */
import request from './index'
import type { CostSummaryResponse, UsageTrendResponse, ReportFilterParams } from '@/types/report'

/** 费用摘要 */
export function getCostSummaryApi(params: ReportFilterParams): Promise<CostSummaryResponse> {
  return request.get('/reports/cost-summary', { params })
}

/** 使用趋势 */
export function getUsageTrendApi(days: number = 30, startDate?: string, endDate?: string): Promise<UsageTrendResponse> {
  const params: Record<string, string | number> = { days }
  if (startDate) params.start_date = startDate
  if (endDate) params.end_date = endDate
  return request.get('/reports/usage-trend', { params })
}
