/**
 * 认证 API
 */
import request from './index'
import type { LoginRequest, LoginResponse, UserInfo, UserCreateRequest, ChangePasswordRequest } from '@/types/user'

/** 登录 */
export function loginApi(data: LoginRequest): Promise<LoginResponse> {
  return request.post('/auth/login', data)
}

/** 获取当前用户信息 */
export function getMeApi(): Promise<UserInfo> {
  return request.get('/auth/me')
}

/** 修改密码 */
export function changePasswordApi(data: ChangePasswordRequest): Promise<{ detail: string }> {
  return request.post('/auth/change-password', data)
}

/** 注册用户 (超管专用) */
export function registerUserApi(data: UserCreateRequest): Promise<{ id: number; username: string; role: string }> {
  return request.post('/auth/register', data)
}
