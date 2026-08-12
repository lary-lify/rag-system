<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">知识库管理</h1>
      <div style="display: flex; gap: var(--space-3)">
        <a-input-search
          v-model:value="filterKeyword"
          placeholder="搜索知识库..."
          style="width: 240px"
          @search="fetchList"
        />
        <a-select v-model:value="filterMode" style="width: 120px" placeholder="模式" allowClear @change="fetchList">
          <a-select-option value="private">私有</a-select-option>
          <a-select-option value="shared">共享</a-select-option>
        </a-select>
        <a-button type="primary" @click="showCreateModal">
          <PlusOutlined /> 新建知识库
        </a-button>
      </div>
    </div>

    <!-- 知识库卡片网格 -->
    <a-spin :spinning="loading">
      <div v-if="kbList.length === 0 && !loading" class="empty-state">
        <div class="empty-state-icon">📚</div>
        <div class="empty-state-text">暂无知识库</div>
        <a-button type="primary" @click="showCreateModal">创建第一个知识库</a-button>
      </div>

      <div class="kb-grid">
        <div
          v-for="kb in kbList"
          :key="kb.id"
          class="kb-card"
          @click="goToDocuments(kb.id)"
        >
          <div class="kb-card-header">
            <div class="kb-card-name">{{ kb.name }}</div>
            <a-tag :color="kb.mode === 'shared' ? 'blue' : 'default'">
              {{ kb.mode === 'shared' ? '共享' : '私有' }}
            </a-tag>
          </div>
          <div class="kb-card-desc">{{ kb.description || '暂无描述' }}</div>
          <div class="kb-card-stats">
            <div class="kb-stat">
              <FileOutlined />
              <span>{{ kb.doc_count }} 文档</span>
            </div>
            <div class="kb-stat">
              <span>{{ kb.chunk_count }} 切片</span>
            </div>
            <div class="kb-stat">
              <span>{{ kb.embedding_model }}</span>
            </div>
            <div class="kb-stat">
              <span>{{ formatDateTime(kb.updated_at, 'MM-DD HH:mm') }}</span>
            </div>
          </div>
          <div class="kb-card-actions">
            <span class="text-secondary text-xs">创建者: {{ kb.owner_name }}</span>
            <div style="display:flex;gap:4px">
              <a-button type="text" size="small" @click.stop="showPermissionModal(kb)">权限</a-button>
              <a-button type="text" size="small" @click.stop="showEditModal(kb)">编辑</a-button>
              <a-popconfirm
                title="确定删除此知识库？此操作不可恢复"
                @confirm="handleDelete(kb.id)"
              >
                <a-button type="text" size="small" danger @click.stop>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="total > pageSize" style="text-align:center;margin-top:var(--space-6)">
        <a-pagination
          v-model:current="currentPage"
          :total="total"
          :page-size="pageSize"
          show-size-changer
          @change="fetchList"
          @showSizeChange="onPageSizeChange"
        />
      </div>
    </a-spin>

    <!-- 创建/编辑弹窗 -->
    <a-modal
      v-model:open="createModalOpen"
      :title="editingKB ? '编辑知识库' : '新建知识库'"
      :footer="null"
      :width="520"
      :destroy-on-close="true"
    >
      <a-form :model="kbForm" layout="vertical" @finish="handleCreateOrUpdate">
        <a-form-item label="名称" name="name" :rules="[{ required: true, message: '请输入知识库名称' }]">
          <a-input v-model:value="kbForm.name" placeholder="知识库名称" />
        </a-form-item>
        <a-form-item label="描述" name="description">
          <a-textarea v-model:value="kbForm.description" placeholder="描述（可选）" :rows="3" />
        </a-form-item>
        <a-form-item label="模式" name="mode">
          <a-radio-group v-model:value="kbForm.mode">
            <a-radio value="private">私有 - 仅授权用户可见</a-radio>
            <a-radio value="shared">共享 - 所有用户可见</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="向量模型" name="embedding_model">
          <a-select v-model:value="kbForm.embedding_model" :disabled="!!editingKB">
            <a-select-option v-for="opt in EMBEDDING_MODEL_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </a-select-option>
          </a-select>
          <div class="form-help">创建后不可修改向量模型</div>
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="submitting" block>
            {{ editingKB ? '保存修改' : '创建知识库' }}
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 权限管理弹窗 -->
    <a-modal
      v-model:open="permissionModalOpen"
      title="权限管理"
      :footer="null"
      :width="600"
      :destroy-on-close="true"
      @open="fetchPermissions"
    >
      <div style="margin-bottom: 12px">
        <a-space>
          <a-auto-complete
            v-model:value="permForm.grantUsername"
            placeholder="输入用户名或姓名搜索"
            style="width: 200px"
            :options="userSearchOptions"
            @search="searchUsers"
            @select="onUserSelect"
          />
          <a-select v-model:value="permForm.grantLevel" style="width: 120px">
            <a-select-option value="read">只读</a-select-option>
            <a-select-option value="upload">可上传</a-select-option>
            <a-select-option value="admin">管理</a-select-option>
          </a-select>
          <a-button type="primary" size="small" @click="handleGrantPerm">授权</a-button>
        </a-space>
      </div>
      <a-table :columns="permColumns" :data-source="permissions" :pagination="false" size="small" row-key="id">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'permission_level'">
            <a-tag :color="permLevelColor[record.permission_level]">{{ permLevelLabel[record.permission_level] || record.permission_level }}</a-tag>
          </template>
          <template v-if="column.key === 'action'">
            <a-popconfirm title="确定撤销此权限？" @confirm="handleRevokePerm(record.user_id)">
              <a-button type="link" size="small" danger>撤销</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, FileOutlined } from '@ant-design/icons-vue'
import {
  listKBsApi, createKBApi, updateKBApi, deleteKBApi,
  listKBPermissionsApi, grantKBPermissionApi, revokeKBPermissionApi,
} from '@/api/knowledgeBases'
import { listUsersApi } from '@/api/users'
import type { KBInfo, KBFilterParams, PermissionInfo, EmbeddingModel } from '@/types/knowledgeBase'
import { EMBEDDING_MODEL_OPTIONS } from '@/types/knowledgeBase'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const kbList = ref<KBInfo[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const filterKeyword = ref('')
const filterMode = ref<string | undefined>(undefined)

async function fetchList() {
  loading.value = true
  try {
    const params: KBFilterParams = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (filterKeyword.value) params.keyword = filterKeyword.value
    if (filterMode.value) params.mode = filterMode.value as 'private' | 'shared'
    const res = await listKBsApi(params)
    kbList.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function goToDocuments(kbId: number) {
  router.push(`/documents?kb_id=${kbId}`)
}

// 创建/编辑
const createModalOpen = ref(false)
const editingKB = ref<KBInfo | null>(null)
const submitting = ref(false)
const kbForm = reactive({ name: '', description: '', mode: 'private' as 'private' | 'shared', embedding_model: 'text-embedding-v3' as EmbeddingModel })

function showCreateModal() {
  editingKB.value = null
  kbForm.name = ''
  kbForm.description = ''
  kbForm.mode = 'private'
  kbForm.embedding_model = 'text-embedding-v3'
  createModalOpen.value = true
}

function showEditModal(kb: KBInfo) {
  editingKB.value = kb
  kbForm.name = kb.name
  kbForm.description = kb.description
  kbForm.mode = kb.mode
  createModalOpen.value = true
}

async function handleCreateOrUpdate() {
  submitting.value = true
  try {
    if (editingKB.value) {
      await updateKBApi(editingKB.value.id, {
        name: kbForm.name,
        description: kbForm.description,
        mode: kbForm.mode,
      })
      message.success('知识库已更新')
    } else {
      await createKBApi({
        name: kbForm.name,
        description: kbForm.description,
        mode: kbForm.mode,
        embedding_model: kbForm.embedding_model,
      })
      message.success('知识库创建成功')
    }
    createModalOpen.value = false
    await fetchList()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(kbId: number) {
  await deleteKBApi(kbId)
  message.success('知识库已删除')
  await fetchList()
}

// 权限管理
const permissionModalOpen = ref(false)
const currentKB = ref<KBInfo | null>(null)
const permissions = ref<PermissionInfo[]>([])
const permForm = reactive({ grantUsername: '', grantLevel: 'read' as 'read' | 'upload' | 'admin' })
const userSearchOptions = ref<{ value: string; label: string }[]>([])

const permLevelLabel: Record<string, string> = { read: '只读', upload: '可上传', admin: '管理' }
const permLevelColor: Record<string, string> = { read: 'default', upload: 'blue', admin: 'green' }

async function searchUsers(keyword: string) {
  if (!keyword || keyword.length < 1) {
    userSearchOptions.value = []
    return
  }
  try {
    const res = await listUsersApi({ page: 1, page_size: 20, keyword })
    userSearchOptions.value = res.items.map((u: any) => ({
      value: u.username,
      label: `${u.username} - ${u.real_name}`,
    }))
  } catch { /* empty */ }
}

function onUserSelect(value: string) {
  permForm.grantUsername = value
}

const permColumns = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '姓名', dataIndex: 'real_name', key: 'real_name' },
  { title: '权限', dataIndex: 'permission_level', key: 'permission_level' },
  { title: '操作', key: 'action', width: 80 },
]

function showPermissionModal(kb: KBInfo) {
  currentKB.value = kb
  permissionModalOpen.value = true
  fetchPermissions()
}

async function fetchPermissions() {
  if (!currentKB.value) return
  try {
    permissions.value = await listKBPermissionsApi(currentKB.value.id)
  } catch { /* empty */ }
}

async function handleGrantPerm() {
  if (!currentKB.value || !permForm.grantUsername) {
    message.warning('请输入用户名')
    return
  }
  try {
    const res: any = await grantKBPermissionApi(currentKB.value.id, {
      username: permForm.grantUsername,
      permission_level: permForm.grantLevel,
    })
    message.success(res?.detail || '操作成功')
    permForm.grantUsername = ''
    await fetchPermissions()
  } catch { /* empty */ }
}

async function handleRevokePerm(userId: number) {
  if (!currentKB.value) return
  await revokeKBPermissionApi(currentKB.value.id, userId)
  message.success('权限已撤销')
  await fetchPermissions()
}

function onPageSizeChange(_current: number, size: number) {
  pageSize.value = size
  fetchList()
}

onMounted(fetchList)
</script>

<style scoped>
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-4);
}

.kb-card {
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.kb-card:hover {
  box-shadow: var(--shadow-sm);
  border-color: var(--brand-500);
  transform: translateY(-2px);
}

.kb-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.kb-card-name {
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  color: var(--color-text-primary);
}

.kb-card-desc {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-4);
  min-height: 20px;
  line-height: 1.5;
}

.kb-card-stats {
  display: flex;
  gap: var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-3);
}

.kb-stat {
  display: flex;
  align-items: center;
  gap: 4px;
}

.kb-card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border-secondary);
}
</style>
