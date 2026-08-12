/**
 * 知识库相关类型定义
 */

import type { PaginatedResponse } from './api'

/** 知识库模式 */
export type KBMode = 'private' | 'shared'

/** 向量模型类型 */
export type EmbeddingModel = 'text-embedding-v3' | 'text-embedding-v2' | 'text-embedding-v1'

/** 向量模型选项 */
export const EMBEDDING_MODEL_OPTIONS: { value: EmbeddingModel; label: string; dimensions: number }[] = [
  { value: 'text-embedding-v3', label: 'text-embedding-v3 (推荐)', dimensions: 1536 },
  { value: 'text-embedding-v2', label: 'text-embedding-v2', dimensions: 1536 },
  { value: 'text-embedding-v1', label: 'text-embedding-v1', dimensions: 1536 },
]

/** 知识库信息 */
export interface KBInfo {
  id: number
  name: string
  description: string
  owner_id: number
  owner_name: string
  mode: KBMode
  embedding_model: EmbeddingModel
  embedding_dimensions: number
  doc_count: number
  chunk_count: number
  is_deleted: boolean
  created_at: string
  updated_at: string
}

/** 知识库列表响应 */
export type KBListResponse = PaginatedResponse<KBInfo>

/** 创建知识库请求 */
export interface KBCreateRequest {
  name: string
  description?: string
  mode: KBMode
  embedding_model?: EmbeddingModel
}

/** 更新知识库请求 */
export interface KBUpdateRequest {
  name?: string
  description?: string
  mode?: KBMode
  embedding_model?: EmbeddingModel
}

/** 权限级别 */
export type PermissionLevel = 'read' | 'upload' | 'admin'

/** 权限信息 */
export interface PermissionInfo {
  id: number
  kb_id: number
  user_id: number
  username: string
  real_name: string
  permission_level: PermissionLevel
  created_at: string
}

/** 授权请求 */
export interface PermissionGrantRequest {
  user_id: number
  permission_level: PermissionLevel
}

/** 知识库筛选 */
export interface KBFilterParams {
  page: number
  page_size: number
  mode?: KBMode
  keyword?: string
}
