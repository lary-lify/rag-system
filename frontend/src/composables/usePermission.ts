/**
 * 角色权限组合式函数
 */
import { useAuthStore } from '@/stores/auth'
import type { UserRole } from '@/types/user'

/** 权限控制 Hook */
export function usePermission() {
  const authStore = useAuthStore()

  /** 检查是否拥有某个角色 */
  function hasRole(roles: UserRole | UserRole[]): boolean {
    const allowed = Array.isArray(roles) ? roles : [roles]
    return allowed.includes(authStore.role)
  }

  /** 是否超管 */
  function isSuperAdmin(): boolean {
    return authStore.isSuperAdmin
  }

  /** 是否部门管理员及以上 */
  function isDeptAdminOrAbove(): boolean {
    return authStore.isDeptAdminOrAbove
  }

  /** 是否普通用户 */
  function isUser(): boolean {
    return authStore.isUser
  }

  return {
    hasRole,
    isSuperAdmin,
    isDeptAdminOrAbove,
    isUser,
    role: authStore.role,
  }
}
