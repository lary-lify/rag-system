/**
 * Vue Router — 基于用户角色的动态路由控制
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/** 所有路由定义 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/components/layout/AppLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
        meta: { title: '首页仪表盘', icon: 'DashboardOutlined', roles: ['super_admin', 'dept_admin'] },
      },
      {
        path: 'knowledge-bases',
        name: 'KnowledgeBases',
        component: () => import('@/views/knowledgeBases/KBListView.vue'),
        meta: { title: '知识库管理', icon: 'BookOutlined', roles: ['super_admin', 'dept_admin'] },
      },
      {
        path: 'documents',
        name: 'Documents',
        component: () => import('@/views/documents/DocumentListView.vue'),
        meta: { title: '文件管理', icon: 'FileOutlined', roles: ['super_admin', 'dept_admin'] },
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/chat/ChatView.vue'),
        meta: { title: '智能问答', icon: 'MessageOutlined', roles: ['super_admin', 'dept_admin', 'user'] },
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('@/views/reports/ReportsView.vue'),
        meta: { title: '统计报表', icon: 'BarChartOutlined', roles: ['super_admin', 'dept_admin'] },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/users/UserListView.vue'),
        meta: { title: '用户管理', icon: 'TeamOutlined', roles: ['super_admin', 'dept_admin'] },
      },
      {
        path: 'audit',
        name: 'Audit',
        component: () => import('@/views/audit/AuditView.vue'),
        meta: { title: '审计日志', icon: 'SafetyOutlined', roles: ['super_admin', 'dept_admin'] },
      },
      {
        path: 'config',
        name: 'Config',
        component: () => import('@/views/config/ConfigView.vue'),
        meta: { title: '系统配置', icon: 'SettingOutlined', roles: ['super_admin', 'dept_admin'] },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 路由守卫 — 权限鉴权 */
router.beforeEach(async (to, _from, next) => {
  // 设置页面标题
  document.title = (to.meta.title as string) || 'RAG知识库系统'

  // 公开页面直接放行
  if (to.meta.public) {
    next()
    return
  }

  const authStore = useAuthStore()

  // 未登录，跳转登录页
  if (!authStore.isLoggedIn) {
    next('/login')
    return
  }

  // 如果还没加载用户信息，先加载
  if (!authStore.userInfo) {
    await authStore.fetchUserInfo()
  }

  // 角色权限检查
  const allowedRoles = to.meta.roles as string[] | undefined
  if (allowedRoles && allowedRoles.length > 0) {
    if (!allowedRoles.includes(authStore.role)) {
      // 无权限，重定向到首页（普通用户只有chat权限时去chat页）
      if (authStore.isUser) {
        next('/chat')
      } else {
        next('/dashboard')
      }
      return
    }
  }

  next()
})

export default router
