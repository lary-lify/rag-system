/**
 * 文档 & 切片相关类型
 */

import type { PaginatedResponse } from './api'

/** 文档处理状态 */
export type DocumentStatus = 'pending' | 'parsing' | 'embedding' | 'completed' | 'failed'

/** 切片策略 */
export type ChunkStrategy = 'fixed_token' | 'semantic' | 'paragraph' | 'heading_level'

/** 文档信息 */
export interface DocumentInfo {
  id: number
  kb_id: number
  filename: string
  original_filename: string
  file_size: number
  file_type: string
  uploader_id: number
  uploader_name: string
  chunk_strategy: ChunkStrategy
  chunk_params: Record<string, unknown>
  chunk_count: number
  status: DocumentStatus
  error_msg: string
  is_deleted: boolean
  created_at: string
}

/** 文档列表响应 */
export type DocumentListResponse = PaginatedResponse<DocumentInfo>

/** 上传文件参数 */
export interface UploadParams {
  kb_id: number
  chunk_strategy: ChunkStrategy
  chunk_params?: Record<string, unknown>
}

/** 切片信息 */
export interface ChunkInfo {
  id: number
  chunk_index: number
  content: string
  token_count: number
}

/** 切片详情 */
export interface ChunkDetail {
  id: number
  document_id: number
  kb_id: number
  content: string
  chunk_index: number
  token_count: number
  metadata: Record<string, unknown>
  milvus_id: number | null
}

/** 切片列表响应 */
export interface ChunkListResponse {
  total: number
  page: number
  page_size: number
  chunks: ChunkInfo[]
}

/** 文档筛选 */
export interface DocumentFilterParams {
  kb_id?: number
  page: number
  page_size: number
  status_filter?: string
}
