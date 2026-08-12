<template>
  <a-layout-sider
    :collapsed="appStore.sidebarCollapsed"
    :width="240"
    :collapsed-width="64"
    class="app-sidebar"
    :trigger="null"
    collapsible
  >
    <!-- Logo 区域 -->
    <div class="sidebar-logo" @click="appStore.toggleSidebar()">
      <div class="logo-icon">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <rect width="28" height="28" rx="6" fill="#2563eb"/>
          <path d="M7 14L12 19L21 9" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <transition name="fade-slide">
        <span v-if="!appStore.sidebarCollapsed" class="logo-text">RAG 知识库</span>
      </transition>
    </div>

    <!-- 导航菜单 -->
    <a-menu
      v-model:selectedKeys="selectedKeys"
      mode="inline"
      theme="dark"
      class="sidebar-menu"
      @click="handleMenuClick"
    >
      <template v-for="item in filteredMenuItems" :key="item.key">
        <a-menu-item>
          <template #icon>
            <component :is="item.icon" />
          </template>
          <span>{{ item.label }}</span>
        </a-menu-item>
      </template>
    </a-menu>

    <!-- 底部用户区 -->
    <div class="sidebar-footer">
      <div class="sidebar-footer-content">
        <a-avatar size="small" style="background: #2563eb">
          {{ authStore.userInfo?.real_name?.charAt(0) || 'U' }}
        </a-avatar>
        <span v-if="!appStore.sidebarCollapsed" class="footer-name">
          {{ authStore.userInfo?.real_name || '未登录' }}
        </span>
      </div>
    </div>
  </a-layout-sider>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import {
  DashboardOutlined,
  BookOutlined,
  FileOutlined,
  MessageOutlined,
  BarChartOutlined,
  TeamOutlined,
  SafetyOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import type { UserRole } from '@/types/user'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const appStore = useAppStore()

/** 菜单项定义 */
interface MenuItem {
  key: string
  label: string
  icon: unknown
  path: string
  roles: UserRole[]
}

const allMenuItems: MenuItem[] = [
  { key: 'dashboard', label: '首页仪表盘', icon: DashboardOutlined, path: '/dashboard', roles: ['super_admin', 'dept_admin'] },
  { key: 'knowledge-bases', label: '知识库管理', icon: BookOutlined, path: '/knowledge-bases', roles: ['super_admin', 'dept_admin'] },
  { key: 'documents', label: '文件管理', icon: FileOutlined, path: '/documents', roles: ['super_admin', 'dept_admin'] },
  { key: 'chat', label: '智能问答', icon: MessageOutlined, path: '/chat', roles: ['super_admin', 'dept_admin', 'user'] },
  { key: 'reports', label: '统计报表', icon: BarChartOutlined, path: '/reports', roles: ['super_admin', 'dept_admin'] },
  { key: 'users', label: '用户管理', icon: TeamOutlined, path: '/users', roles: ['super_admin', 'dept_admin'] },
  { key: 'audit', label: '审计日志', icon: SafetyOutlined, path: '/audit', roles: ['super_admin', 'dept_admin'] },
  { key: 'config', label: '系统配置', icon: SettingOutlined, path: '/config', roles: ['super_admin', 'dept_admin'] },
]

/** 根据角色过滤菜单 */
const filteredMenuItems = computed(() => {
  const role = authStore.role
  return allMenuItems.filter((item) => item.roles.includes(role))
})

/** 选中菜单项 */
const selectedKeys = ref<string[]>([route.path.split('/')[1] || 'dashboard'])

function handleMenuClick({ key }: { key: string }) {
  const item = allMenuItems.find((m) => m.key === key)
  if (item) {
    router.push(item.path)
  }
}
</script>

<style scoped>
.app-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  z-index: 100;
  overflow: hidden;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-logo {
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  cursor: pointer;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  user-select: none;
}

.logo-text {
  font-size: var(--text-lg);
  font-weight: var(--weight-bold);
  color: #ffffff;
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  padding: var(--space-2) var(--space-2);
  overflow-y: auto;
  border-right: none;
}

.sidebar-footer {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-footer-content {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.footer-name {
  font-size: var(--text-sm);
  color: var(--sidebar-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
