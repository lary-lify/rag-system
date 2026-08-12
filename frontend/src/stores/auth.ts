/**
 * 认证状态管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo, UserRole } from '@/types/user'
import { getMeApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const userInfo = ref<UserInfo | null>(null)
  const isLoggedIn = computed(() => !!token.value)

  /** 当前用户角色 */
  const role = computed<UserRole>(() => userInfo.value?.role || 'user')

  /** 是否是超管 */
  const isSuperAdmin = computed(() => role.value === 'super_admin')

  /** 是否是部门管理员及以上 */
  const isDeptAdminOrAbove = computed(() => role.value === 'super_admin' || role.value === 'dept_admin')

  /** 是否为普通用户 */
  const isUser = computed(() => role.value === 'user')

  /** 设置 Token */
  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('access_token', newToken)
  }

  /** 设置用户信息 */
  function setUserInfo(info: UserInfo) {
    userInfo.value = info
    localStorage.setItem('user_info', JSON.stringify(info))
  }

  /** 获取用户信息 (从后端刷新) */
  async function fetchUserInfo() {
    try {
      const info = await getMeApi()
      setUserInfo(info)
      return info
    } catch {
      // 如果获取失败，尝试从本地缓存恢复
      const cached = localStorage.getItem('user_info')
      if (cached) {
        userInfo.value = JSON.parse(cached)
      }
      return null
    }
  }

  /** 登出 */
  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
  }

  return {
    token,
    userInfo,
    isLoggedIn,
    role,
    isSuperAdmin,
    isDeptAdminOrAbove,
    isUser,
    setToken,
    setUserInfo,
    fetchUserInfo,
    logout,
  }
})
