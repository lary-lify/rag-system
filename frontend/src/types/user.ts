/**
 * 用户 & 权限相关类型定义
 */

/** 角色枚举 */
export type UserRole = 'super_admin' | 'dept_admin' | 'user'

/** 用户状态 */
export type UserStatus = 'active' | 'disabled'

/** 用户信息（后端返回） */
export interface UserInfo {
  id: number
  username: string
  real_name: string
  email: string
  phone: string
  dept_name: string
  role: UserRole
  status: UserStatus
  created_at: string
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user_info: {
    id: number
    username: string
    real_name: string
    role: UserRole
  }
}

/** 登录请求 */
export interface LoginRequest {
  username: string
  password: string
}

/** 注册用户请求 */
export interface UserCreateRequest {
  username: string
  password: string
  real_name: string
  email: string
  phone: string
  dept_name: string
  role: UserRole
}

/** 更新用户请求 */
export interface UserUpdateRequest {
  real_name?: string
  email?: string
  phone?: string
  dept_name?: string
  status?: UserStatus
}

/** 修改密码请求 */
export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

/** 用户列表筛选 */
export interface UserFilterParams {
  page: number
  page_size: number
  role?: UserRole
  dept_name?: string
  keyword?: string
}
