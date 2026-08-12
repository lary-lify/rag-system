/**
 * 知识库 API
 */
import request from './index'
import type {
  KBInfo, KBCreateRequest, KBUpdateRequest, KBListResponse, KBFilterParams,
  PermissionInfo, PermissionGrantRequest,
} from '@/types/knowledgeBase'

/** 创建知识库 */
export function createKBApi(data: KBCreateRequest): Promise<KBInfo> {
  return request.post('/knowledge-bases', data)
}

/** 知识库列表 */
export function listKBsApi(params: KBFilterParams): Promise<KBListResponse> {
  return request.get('/knowledge-bases', { params })
}

/** 知识库详情 */
export function getKBApi(kbId: number): Promise<KBInfo> {
  return request.get(`/knowledge-bases/${kbId}`)
}

/** 更新知识库 */
export function updateKBApi(kbId: number, data: KBUpdateRequest): Promise<{ detail: string; id: number }> {
  return request.put(`/knowledge-bases/${kbId}`, data)
}

/** 删除知识库 */
export function deleteKBApi(kbId: number): Promise<{ detail: string; id: number }> {
  return request.delete(`/knowledge-bases/${kbId}`)
}

/** 获取知识库权限列表 */
export function listKBPermissionsApi(kbId: number): Promise<PermissionInfo[]> {
  return request.get(`/knowledge-bases/${kbId}/permissions`)
}

/** 授权 */
export function grantKBPermissionApi(kbId: number, data: PermissionGrantRequest): Promise<{ id: number; detail: string }> {
  return request.post(`/knowledge-bases/${kbId}/permissions`, data)
}

/** 撤销权限 */
export function revokeKBPermissionApi(kbId: number, userId: number): Promise<void> {
  return request.delete(`/knowledge-bases/${kbId}/permissions/${userId}`)
}
