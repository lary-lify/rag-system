<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <rect width="40" height="40" rx="8" fill="#2563eb"/>
            <path d="M10 20L17 27L30 13" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h1 class="login-title">RAG 知识库系统</h1>
        <p class="login-subtitle">企业级智能问答平台</p>
      </div>

      <a-form
        :model="formState"
        layout="vertical"
        class="login-form"
        @finish="handleLogin"
      >
        <a-form-item
          name="username"
          :rules="[{ required: true, message: '请输入用户名' }]"
        >
          <a-input
            v-model:value="formState.username"
            size="large"
            placeholder="用户名"
            :prefix="h(UserOutlined)"
            autocomplete="username"
          />
        </a-form-item>

        <a-form-item
          name="password"
          :rules="[{ required: true, message: '请输入密码' }]"
        >
          <a-input-password
            v-model:value="formState.password"
            size="large"
            placeholder="密码"
            :prefix="h(LockOutlined)"
            autocomplete="current-password"
            @keydown.enter="handleLogin"
          />
        </a-form-item>

        <a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            size="large"
            :loading="loading"
            block
          >
            {{ loading ? '登录中...' : '登 录' }}
          </a-button>
        </a-form-item>
      </a-form>

      <div class="login-footer">
        <span class="text-tertiary text-xs">默认超管: admin / admin123</span>
      </div>
    </div>

    <!-- 背景装饰 -->
    <div class="login-bg-decoration">
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { h, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { UserOutlined, LockOutlined } from '@ant-design/icons-vue'
import { loginApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const formState = reactive({
  username: '',
  password: '',
})

const loading = ref(false)

async function handleLogin() {
  loading.value = true
  try {
    const res = await loginApi({
      username: formState.username,
      password: formState.password,
    })

    authStore.setToken(res.access_token)
    authStore.setUserInfo({
      id: res.user_info.id,
      username: res.user_info.username,
      real_name: res.user_info.real_name,
      email: '',
      phone: '',
      dept_name: '',
      role: res.user_info.role,
      status: 'active',
      created_at: '',
    })

    message.success('登录成功')

    // 根据角色跳转
    if (res.user_info.role === 'user') {
      router.push('/chat')
    } else {
      router.push('/dashboard')
    }
  } catch {
    // 错误由请求拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 50%, #bfdbfe 100%);
  position: relative;
  overflow: hidden;
}

.login-card {
  background: var(--gray-0);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-xl);
  padding: var(--space-10);
  width: 420px;
  z-index: 2;
}

.login-header {
  text-align: center;
  margin-bottom: var(--space-8);
}

.login-logo {
  margin-bottom: var(--space-4);
}

.login-title {
  font-size: var(--text-xl);
  font-weight: var(--weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
}

.login-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.login-form {
  margin-top: var(--space-4);
}

.login-footer {
  text-align: center;
  margin-top: var(--space-4);
}

/* 背景装饰 */
.login-bg-decoration {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.15;
}

.bg-circle-1 {
  width: 600px;
  height: 600px;
  background: var(--brand-500);
  top: -200px;
  right: -100px;
}

.bg-circle-2 {
  width: 400px;
  height: 400px;
  background: var(--brand-700);
  bottom: -150px;
  left: -80px;
}

[data-theme="dark"] .login-page {
  background: linear-gradient(135deg, #0b1120 0%, #0f172a 50%, #1e293b 100%);
}
</style>
