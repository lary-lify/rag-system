/**
 * 报表 & 计费 相关类型
 */

/** 费用摘要 */
export interface CostSummaryResponse {
  period_start: string
  period_end: string
  total_embedding_tokens: number
  total_chat_input_tokens: number
  total_chat_output_tokens: number
  total_estimated_cost: number
  by_user: UserCostItem[]
  by_kb: KBCostItem[]
  by_day: DailyCostItem[]
}

/** 用户维度费用项 */
export interface UserCostItem {
  user_id: number
  username: string
  tokens: number
  cost: number
}

/** 知识库维度费用项 */
export interface KBCostItem {
  kb_id: number
  kb_name: string
  tokens: number
  cost: number
}

/** 每日费用项 */
export interface DailyCostItem {
  date: string
  embedding_cost: number
  chat_cost: number
  total_cost: number
}

/** 使用趋势 */
export interface UsageTrendResponse {
  dates: string[]
  embedding_tokens: number[]
  chat_input_tokens: number[]
  chat_output_tokens: number[]
  costs: number[]
}

/** 报表筛选参数 */
export interface ReportFilterParams {
  start_date?: string
  end_date?: string
  user_id?: number
  kb_id?: number
  days?: number
}
