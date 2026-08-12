/**
 * 对话 & SSE流式相关类型
 */

import type { PaginatedResponse } from './api'

/** 对话信息 */
export interface ConversationInfo {
  id: number
  user_id: number
  title: string
  kb_ids: number[]
  message_count: number
  is_deleted: boolean
  created_at: string
  updated_at: string
}

/** 对话列表响应 */
export type ConversationListResponse = PaginatedResponse<ConversationInfo>

/** 创建对话 */
export interface ConversationCreateRequest {
  title?: string
  kb_ids: number[]
}

/** 更新对话 */
export interface ConversationUpdateRequest {
  title?: string
}

/** 发送消息请求 */
export interface ChatRequest {
  conversation_id?: number | null
  question: string
  kb_ids: number[]
}

/** 消息历史项 */
export interface MessageHistoryItem {
  id: number
  question: string
  answer: string
  source_chunks: SourceChunk[]
  input_tokens: number
  output_tokens: number
  feedback: number | null
  created_at: string
}

/** 来源切片信息 */
export interface SourceChunk {
  chunk_id: number
  document_name: string
  content: string
  score: number
  metadata?: Record<string, unknown>
}

/** SSE事件类型 */
export type SSEEventType = 
  | 'conversation_id'
  | 'chunk' 
  | 'source_chunks' 
  | 'usage'
  | 'done'
  | 'error'

/** SSE流式数据块 */
export interface SSEChunk {
  type: 'chunk'
  content: string
}

/** SSE来源切片事件 */
export interface SSESourceChunks {
  type: 'source_chunks'
  chunks: SourceChunk[]
}

/** SSE对话ID事件 */
export interface SSEConversationId {
  type: 'conversation_id'
  value: number
}

/** SSE完成事件 */
export interface SSEDone {
  type: 'done'
  message_id: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
}

/** SSE错误事件 */
export interface SSEError {
  type: 'error'
  detail: string
}

/** SSE联合类型 */
export type SSEEvent = 
  | SSEConversationId 
  | SSEChunk 
  | SSESourceChunks 
  | SSEDone 
  | SSEError

/** 对话导出行 */
export interface ConversationExportRow {
  time: string
  operator: string
  knowledge_base: string
  question: string
  answer: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost: number
  sources: string
}
