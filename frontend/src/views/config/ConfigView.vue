<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">系统配置</h1>
      <a-tag color="blue">只读</a-tag>
    </div>

    <a-spin :spinning="loading">
      <!-- 配置按模块分组展示 -->
      <div v-for="group in configGroups" :key="group.name" class="card" style="margin-bottom:var(--space-6)">
        <div class="card-header">{{ group.name }}</div>
        <div class="card-body" style="padding:0">
          <a-table
            :columns="configColumns"
            :data-source="group.items"
            :pagination="false"
            size="small"
            row-key="key"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'value'">
                <code class="config-value">{{ record.value }}</code>
              </template>
              <template v-if="column.key === 'key'">
                <code class="config-key">{{ record.key }}</code>
              </template>
            </template>
          </a-table>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getConfigViewApi } from '@/api/config'
import type { ConfigItem } from '@/types/audit'

const loading = ref(false)
const configItems = ref<ConfigItem[]>([])

/** 配置分组 */
const configGroups = computed(() => {
  const items = configItems.value
  const groups: { name: string; keys: string[] }[] = [
    { name: '应用基础', keys: ['APP_NAME', 'APP_ENV', 'APP_PORT', 'JWT_EXPIRE_HOURS', 'INIT_ADMIN_USERNAME'] },
    { name: 'MySQL 数据库', keys: ['MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DATABASE', 'MYSQL_USER'] },
    { name: 'Milvus 向量库', keys: ['MILVUS_HOST', 'MILVUS_PORT', 'MILVUS_INDEX_TYPE', 'MILVUS_METRIC_TYPE'] },
    { name: '检索参数', keys: ['RAG_TOP_K', 'RAG_SCORE_THRESHOLD', 'RAG_RETRIEVE_MODE'] },
    { name: '阿里通义向量', keys: ['TONGYI_API_KEY', 'TONGYI_EMBEDDING_MODEL', 'TONGYI_EMBEDDING_DIMENSIONS', 'TONGYI_EMBEDDING_TOKEN_PRICE'] },
    { name: 'DeepSeek 对话', keys: ['DEEPSEEK_API_KEY', 'DEEPSEEK_CHAT_MODEL', 'DEEPSEEK_INPUT_TOKEN_PRICE', 'DEEPSEEK_OUTPUT_TOKEN_PRICE'] },
    { name: '文件上传', keys: ['UPLOAD_MAX_SIZE_MB', 'UPLOAD_ALLOWED_EXTENSIONS'] },
    { name: '切片默认', keys: ['DEFAULT_CHUNK_STRATEGY', 'DEFAULT_CHUNK_SIZE', 'DEFAULT_CHUNK_OVERLAP'] },
  ]

  return groups
    .map((g) => ({
      name: g.name,
      items: items.filter((i) => g.keys.includes(i.key)),
    }))
    .filter((g) => g.items.length > 0)
})

const configColumns = [
  { title: '配置项', key: 'key', width: 250 },
  { title: '当前值', key: 'value', width: 300 },
  { title: '说明', dataIndex: 'description', key: 'description' },
]

onMounted(async () => {
  loading.value = true
  try {
    const res = await getConfigViewApi()
    configItems.value = res.config_items
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.config-key {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  background: var(--color-bg-secondary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.config-value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--brand-600);
}
</style>
