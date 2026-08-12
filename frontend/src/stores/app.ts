/**
 * 应用全局状态管理
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

export const useAppStore = defineStore('app', () => {
  // 主题
  const theme = ref<ThemeMode>(
    (localStorage.getItem('app_theme') as ThemeMode) || 'light'
  )

  // 侧边栏折叠
  const sidebarCollapsed = ref(false)

  /** 切换主题 */
  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
    localStorage.setItem('app_theme', theme.value)
    document.documentElement.setAttribute('data-theme', theme.value)
  }

  /** 设置主题 */
  function setTheme(mode: ThemeMode) {
    theme.value = mode
    localStorage.setItem('app_theme', mode)
    document.documentElement.setAttribute('data-theme', mode)
  }

  /** 初始化主题 */
  function initTheme() {
    const saved = localStorage.getItem('app_theme') as ThemeMode | null
    if (saved) {
      setTheme(saved)
    }
  }

  /** 切换侧边栏 */
  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    theme,
    sidebarCollapsed,
    toggleTheme,
    setTheme,
    initTheme,
    toggleSidebar,
  }
})
