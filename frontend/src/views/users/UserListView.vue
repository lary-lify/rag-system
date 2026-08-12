<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">用户管理</h1>
      <div style="display:flex;gap:12px">
        <a-input-search v-model:value="filterKeyword" placeholder="搜索用户..." style="width:200px" @search="fetchList" />
        <a-select v-model:value="filterRole" style="width:140px" placeholder="角色" allowClear @change="fetchList">
          <a-select-option value="super_admin">超级管理员</a-select-option>
          <a-select-option value="dept_admin">部门管理员</a-select-option>
          <a-select-option value="user">普通用户</a-select-option>
        </a-select>
        <a-button v-if="isSuperAdmin()" type="primary" @click="showCreateModal">
          <PlusOutlined /> 新建用户
        </a-button>
      </div>
    </div>

    <div class="table-card">
      <a-table
        :columns="columns"
        :data-source="userList"
        :loading="loading"
        :pagination="{ current: currentPage, total, pageSize, onChange: onPageChange }"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'role'">
            <a-tag :color="getRoleColor(record.role)">{{ getRoleLabel(record.role) }}</a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="getUserStatusColor(record.status)">{{ getUserStatusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button
                v-if="isSuperAdmin() || (record.role !== 'super_admin' && record.role !== 'dept_admin')"
                type="link" size="small" @click="showEditModal(record)"
              >编辑</a-button>
              <a-button
                v-if="isSuperAdmin() || (record.role !== 'super_admin' && record.role !== 'dept_admin')"
                type="link" size="small"
                @click="handleToggleStatus(record)"
              >
                {{ record.status === 'active' ? '禁用' : '启用' }}
              </a-button>
              <a-popconfirm
                v-if="isSuperAdmin() && record.role !== 'super_admin'"
                title="确定删除此用户？"
                @confirm="handleDelete(record.id)"
              >
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <!-- 创建/编辑弹窗 -->
    <a-modal
      v-model:open="modalOpen"
      :title="editingUser ? '编辑用户' : '新建用户'"
      :footer="null"
      :width="520"
      :destroy-on-close="true"
    >
      <a-form :model="userForm" layout="vertical" @finish="handleSubmit">
        <a-form-item label="用户名" name="username" :rules="[{ required: true }]">
          <a-input v-model:value="userForm.username" :disabled="!!editingUser" />
        </a-form-item>
        <a-form-item v-if="!editingUser" label="密码" name="password" :rules="[{ required: true, min: 6 }]">
          <a-input-password v-model:value="userForm.password" />
        </a-form-item>
        <a-form-item label="姓名" name="real_name">
          <a-input v-model:value="userForm.real_name" />
        </a-form-item>
        <a-form-item label="邮箱" name="email">
          <a-input v-model:value="userForm.email" />
        </a-form-item>
        <a-form-item label="手机" name="phone">
          <a-input v-model:value="userForm.phone" />
        </a-form-item>
        <a-form-item label="部门" name="dept_name">
          <a-input v-model:value="userForm.dept_name" />
        </a-form-item>
        <a-form-item v-if="isSuperAdmin() && !editingUser" label="角色" name="role">
          <a-select v-model:value="userForm.role">
            <a-select-option value="super_admin">超级管理员</a-select-option>
            <a-select-option value="dept_admin">部门管理员</a-select-option>
            <a-select-option value="user">普通用户</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="submitting" block>
            {{ editingUser ? '保存' : '创建' }}
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { listUsersApi, updateUserApi, deleteUserApi } from '@/api/users'
import { registerUserApi } from '@/api/auth'
import type { UserInfo } from '@/types/user'
import { formatDateTime, getRoleLabel, getRoleColor, getUserStatusLabel, getUserStatusColor } from '@/utils/format'
import { usePermission } from '@/composables/usePermission'

const { isSuperAdmin } = usePermission()

const loading = ref(false)
const userList = ref<UserInfo[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const filterKeyword = ref('')
const filterRole = ref<string | undefined>(undefined)

const columns = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '姓名', dataIndex: 'real_name', key: 'real_name' },
  { title: '邮箱', dataIndex: 'email', key: 'email', ellipsis: true },
  { title: '部门', dataIndex: 'dept_name', key: 'dept', ellipsis: true },
  { title: '角色', key: 'role', width: 110 },
  { title: '状态', key: 'status', width: 80 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 220 },
]

async function fetchList() {
  loading.value = true
  try {
    const res = await listUsersApi({
      page: currentPage.value,
      page_size: pageSize.value,
      ...(filterRole.value ? { role: filterRole.value as any } : {}),
      ...(filterKeyword.value ? { keyword: filterKeyword.value } : {}),
    })
    userList.value = res.items
    total.value = res.total
  } finally { loading.value = false }
}

const modalOpen = ref(false)
const editingUser = ref<UserInfo | null>(null)
const submitting = ref(false)
const userForm = reactive({
  username: '', password: '', real_name: '', email: '', phone: '',
  dept_name: '', role: 'user' as string,
})

function showCreateModal() {
  editingUser.value = null
  Object.assign(userForm, { username: '', password: '', real_name: '', email: '', phone: '', dept_name: '', role: 'user' })
  modalOpen.value = true
}

function showEditModal(user: UserInfo) {
  editingUser.value = user
  Object.assign(userForm, {
    username: user.username, password: '', real_name: user.real_name,
    email: user.email, phone: user.phone, dept_name: user.dept_name, role: user.role,
  })
  modalOpen.value = true
}

async function handleSubmit() {
  submitting.value = true
  try {
    if (editingUser.value) {
      await updateUserApi(editingUser.value.id, {
        real_name: userForm.real_name,
        email: userForm.email,
        phone: userForm.phone,
        dept_name: userForm.dept_name,
      })
      message.success('用户已更新')
    } else {
      await registerUserApi(userForm as any)
      message.success('用户创建成功')
    }
    modalOpen.value = false
    await fetchList()
  } finally { submitting.value = false }
}

async function handleToggleStatus(user: UserInfo) {
  const newStatus = user.status === 'active' ? 'disabled' : 'active'
  await updateUserApi(user.id, { status: newStatus })
  message.success(`用户已${newStatus === 'active' ? '启用' : '禁用'}`)
  await fetchList()
}

async function handleDelete(userId: number) {
  await deleteUserApi(userId)
  message.success('用户已删除')
  await fetchList()
}

function onPageChange(page: number) {
  currentPage.value = page
  fetchList()
}

onMounted(fetchList)
</script>
