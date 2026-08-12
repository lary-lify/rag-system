<template>
  <a-layout-header class="topbar">
    <div class="topbar-left">
      <!-- 折叠按钮 -->
      <a-button
        type="text"
        class="collapse-btn"
        @click="appStore.toggleSidebar()"
      >
        <MenuFoldOutlined v-if="!appStore.sidebarCollapsed" />
        <MenuUnfoldOutlined v-else />
      </a-button>

      <!-- 面包屑 -->
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <HomeOutlined />
        </a-breadcrumb-item>
        <a-breadcrumb-item>{{ currentTitle }}</a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <div class="topbar-right">
      <!-- 主题切换 -->
      <a-tooltip :title="appStore.theme === 'light' ? '切换深色主题' : '切换浅色主题'">
        <a-button type="text" class="topbar-action-btn" @click="appStore.toggleTheme()">
          <BulbOutlined />
        </a-button>
      </a-tooltip>

      <!-- 用户下拉菜单 -->
      <a-dropdown>
        <div class="user-dropdown-trigger">
          <a-avatar size="small" style="background: #2563eb">
            {{ authStore.userInfo?.real_name?.charAt(0) || 'U' }}
          </a-avatar>
          <span class="user-name">{{ authStore.userInfo?.real_name }}</span>
          <DownOutlined style="font-size: 10px; color: var(--color-text-tertiary)" />
        </div>
        <template #overlay>
          <a-menu @click="handleUserMenu">
            <a-menu-item key="profile">
              <UserOutlined />
              <span style="margin-left: 8px">个人信息</span>
            </a-menu-item>
            <a-menu-item key="password">
              <LockOutlined />
              <span style="margin-left: 8px">修改密码</span>
            </a-menu-item>
            <a-menu-divider />
            <a-menu-item key="logout" danger>
              <LogoutOutlined />
              <span style="margin-left: 8px">退出登录</span>
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>

    <!-- 修改密码弹窗 -->
    <a-modal
      v-model:open="passwordModalVisible"
      title="修改密码"
      :footer="null"
      :width="440"
      :destroy-on-close="true"
    >
      <a-form
        :model="passwordForm"
        layout="vertical"
        @finish="handleChangePassword"
      >
        <a-form-item label="当前密码" name="old_password" :rules="[{ required: true, message: '请输入当前密码' }]">
          <a-input-password v-model:value="passwordForm.old_password" placeholder="请输入当前密码" />
        </a-form-item>
        <a-form-item label="新密码" name="new_password" :rules="[{ required: true, min: 6, message: '密码至少6位' }]">
          <a-input-password v-model:value="passwordForm.new_password" placeholder="请输入新密码（至少6位）" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="changing" block>确认修改</a-button>
        </a-form-item>
      </a-form>
    </a-modal>
  </a-layout-header>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import {
  HomeOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BulbOutlined,
  DownOutlined,
  UserOutlined,
  LockOutlined,
  LogoutOutlined,
} from '@ant-design/icons-vue'
import { changePasswordApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const appStore = useAppStore()

/** 当前页面标题 */
const currentTitle = computed(() => route.meta.title as string || '')

/** 修改密码 */
const passwordModalVisible = ref(false)
const changing = ref(false)
const passwordForm = ref({ old_password: '', new_password: '' })

/** 用户菜单点击 */
function handleUserMenu({ key }: { key: string }) {
  switch (key) {
    case 'profile':
      message.info('个人信息页面待开发')
      break
    case 'password':
      passwordModalVisible.value = true
      break
    case 'logout':
      authStore.logout()
      router.push('/login')
      break
  }
}

/** 修改密码 */
async function handleChangePassword() {
  changing.value = true
  try {
    await changePasswordApi({
      old_password: passwordForm.value.old_password,
      new_password: passwordForm.value.new_password,
    })
    message.success('密码修改成功')
    passwordModalVisible.value = false
    passwordForm.value = { old_password: '', new_password: '' }
  } catch {
    // 错误由拦截器统一处理
  } finally {
    changing.value = false
  }
}
</script>

<style scoped>
.topbar {
  height: var(--topbar-height);
  background: var(--topbar-bg);
  border-bottom: 1px solid var(--topbar-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  line-height: var(--topbar-height);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.collapse-btn {
  font-size: 18px;
  color: var(--color-text-secondary);
}

.breadcrumb {
  font-size: var(--text-sm);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.topbar-action-btn {
  font-size: 18px;
  color: var(--color-text-secondary);
}

.user-dropdown-trigger {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.user-dropdown-trigger:hover {
  background: var(--color-bg-hover);
}

.user-name {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
