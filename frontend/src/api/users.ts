/**
 * 用户管理 API
 */
import request from './index'
import type { UserInfo, UserUpdateRequest, UserFilterParams } from '@/types/user'
import type { PaginatedResponse } from '@/types/api'

/** 用户列表 */
export function listUsersApi(params: UserFilterParams): Promise<PaginatedResponse<UserInfo>> {
  return request.get('/users', { params })
}

/** 用户详情 */
export function getUserApi(userId: number): Promise<UserInfo> {
  return request.get(`/users/${userId}`)
}

/** 更新用户 */
export function updateUserApi(userId: number, data: UserUpdateRequest): Promise<{ detail: string; id: number }> {
  return request.put(`/users/${userId}`, data)
}

/** 删除用户 (软删除/禁用) */
export function deleteUserApi(userId: number): Promise<void> {
  return request.delete(`/users/${userId}`)
}
