<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">审计日志</h1>
      <div style="display:flex;gap:12px">
        <a-select v-model:value="filterAction" style="width:140px" placeholder="操作类型" allowClear @change="fetchList">
          <a-select-option v-for="item in actionOptions" :key="item.value" :value="item.value">{{ item.label }}</a-select-option>
        </a-select>
        <a-select v-model:value="filterResource" style="width:140px" placeholder="资源类型" allowClear @change="fetchList">
          <a-select-option v-for="item in resourceOptions" :key="item.value" :value="item.value">{{ item.label }}</a-select-option>
        </a-select>
        <a-button @click="handleExport">
          <DownloadOutlined /> 导出CSV
        </a-button>
      </div>
    </div>

    <div class="table-card">
      <a-table
        :columns="columns"
        :data-source="logs"
        :loading="loading"
        :pagination="{ current: page, total, pageSize, onChange: onPageChange }"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <a-tag :color="actionColorMap[record.action] || 'default'">
              {{ actionLabelMap[record.action] || record.action }}
            </a-tag>
          </template>
          <template v-if="column.key === 'resource_type'">
            <a-tag color="blue">
              {{ resourceLabelMap[record.resource_type] || record.resource_type }}
            </a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>
          <template v-if="column.key === 'detail'">
            <span style="white-space:normal;line-height:1.4">
              {{ formatDetail(record.detail, record.action) }}
            </span>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { DownloadOutlined } from '@ant-design/icons-vue'
import { listAuditLogsApi, exportAuditLogsApi } from '@/api/audit'
import type { AuditLogInfo } from '@/types/audit'
import { formatDateTime } from '@/utils/format'
import { saveAs } from 'file-saver'

const loading = ref(false)
const logs = ref<AuditLogInfo[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterAction = ref<string | undefined>(undefined)
const filterResource = ref<string | undefined>(undefined)

// ---- 操作类型映射 ----
const actionLabelMap: Record<string, string> = {
  login: '登录',
  create: '创建',
  update: '更新',
  delete: '删除',
  upload: '上传',
  export: '导出',
  grant_permission: '授权',
  revoke_permission: '撤销权限',
  config_view: '查看配置',
  chunking: '分块',
}

const actionColorMap: Record<string, string> = {
  login: 'green',
  create: 'blue',
  update: 'orange',
  delete: 'red',
  upload: 'cyan',
  export: 'purple',
  grant_permission: 'green',
  revoke_permission: 'volcano',
  config_view: 'default',
  chunking: 'geekblue',
}

const actionOptions = Object.entries(actionLabelMap).map(([value, label]) => ({ value, label }))

// ---- 资源类型映射 ----
const resourceLabelMap: Record<string, string> = {
  user: '用户',
  knowledge_base: '知识库',
  document: '文档',
  chunk: '文本片段',
  conversation: '对话',
  message: '消息',
  kb_permission: '知识库权限',
  system_config: '系统配置',
  token_usage: 'Token用量',
}

const resourceOptions = Object.entries(resourceLabelMap).map(([value, label]) => ({ value, label }))

// ---- 权限级别映射 ----
const permLevelLabel: Record<string, string> = { read: '只读', upload: '可上传', admin: '管理' }

// ---- 详情格式化 ----
function formatDetail(detail: any, action: string): string {
  if (!detail || typeof detail !== 'object') return String(detail || '')
  const d = detail as Record<string, any>

  // 辅助：显示目标用户
  const userDisplay = d.target_username || (d.target_user_id ? '#' + d.target_user_id : '')

  switch (action) {
    case 'login':
      return d.method === 'password' ? '密码登录' : d.method || '登录'
    case 'grant_permission': {
      const levelLabel = permLevelLabel[d.level] || d.level || ''
      const kbDisplay = d.kb_name || (d.kb_id ? '#' + d.kb_id : '')
      return `为用户「${userDisplay}」授权知识库${kbDisplay ? '「' + kbDisplay + '」' : ''}，权限: ${levelLabel}`
    }
    case 'revoke_permission': {
      const kbDisplay = d.kb_name || (d.kb_id ? '#' + d.kb_id : '')
      return `撤销用户「${userDisplay}」的知识库${kbDisplay ? '「' + kbDisplay + '」' : ''}权限`
    }
    case 'create':
      return `创建${resourceLabelMap[d.resource_type] || d.resource_type || ''}${d.name ? '「' + d.name + '」' : ''}`
    case 'update':
      return `更新${resourceLabelMap[d.resource_type] || d.resource_type || ''}${d.name ? '「' + d.name + '」' : ''}`
    case 'delete':
      return `删除${resourceLabelMap[d.resource_type] || d.resource_type || ''}${d.name ? '「' + d.name + '」' : ''}`
    case 'upload':
      return d.filename ? `上传「${d.filename}」` : '上传文件'
    case 'export':
      return d.format ? `导出${d.format}格式` : '导出数据'
    case 'config_view':
      return '查看系统配置'
    case 'chunking':
      return `分块处理${d.doc_id ? '文档#' + d.doc_id : ''}`
    default:
      return JSON.stringify(detail)
  }
}

function formatDetailFull(detail: any): string {
  if (!detail) return ''
  return JSON.stringify(detail, null, 2)
}

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
  { title: '用户', dataIndex: 'username', key: 'username', width: 100 },
  { title: '操作', key: 'action', width: 110 },
  { title: '资源类型', key: 'resource_type', width: 110 },
  { title: '资源ID', dataIndex: 'resource_id', key: 'resource_id', width: 80 },
  { title: '详情', key: 'detail' },
  { title: 'IP', dataIndex: 'ip_address', key: 'ip', width: 130 },
  { title: '时间', key: 'created_at', width: 160 },
]

async function fetchList() {
  loading.value = true
  try {
    const res = await listAuditLogsApi({
      page: page.value,
      page_size: pageSize.value,
      ...(filterAction.value ? { action: filterAction.value } : {}),
      ...(filterResource.value ? { resource_type: filterResource.value } : {}),
    })
    logs.value = res.items
    total.value = res.total
  } finally { loading.value = false }
}

async function handleExport() {
  try {
    const blob = await exportAuditLogsApi({
      ...(filterAction.value ? { action: filterAction.value } : {}),
      ...(filterResource.value ? { resource_type: filterResource.value } : {}),
    })
    saveAs(blob, '审计日志.csv')
    message.success('导出成功')
  } catch { /* empty */ }
}

function onPageChange(p: number) {
  page.value = p
  fetchList()
}

onMounted(fetchList)
</script>
