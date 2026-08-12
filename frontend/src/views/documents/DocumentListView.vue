<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">文件管理</h1>
      <div style="display:flex;gap:12px">
        <a-select
          v-model:value="filterKBId"
          style="width:200px"
          placeholder="选择知识库"
          allowClear
          @change="fetchList"
        >
          <a-select-option v-for="kb in kbOptions" :key="kb.id" :value="kb.id">
            {{ kb.name }}
          </a-select-option>
        </a-select>
        <a-select v-model:value="filterStatus" style="width:120px" placeholder="状态" allowClear @change="fetchList">
          <a-select-option value="completed">入库成功</a-select-option>
          <a-select-option value="pending">待处理</a-select-option>
          <a-select-option value="parsing">解析中</a-select-option>
          <a-select-option value="embedding">向量化中</a-select-option>
          <a-select-option value="failed">入库失败</a-select-option>
        </a-select>
        <a-button type="primary" @click="openUploadModal">
          <UploadOutlined /> 上传文件
        </a-button>
      </div>
    </div>

    <!-- 文件表格 -->
    <div class="table-card">
      <div class="table-toolbar">
        <span class="text-secondary text-sm">共 {{ total }} 个文件</span>
      </div>
      <a-table
        :columns="columns"
        :data-source="docList"
        :loading="loading"
        :pagination="{ current: currentPage, total, pageSize, onChange: onPageChange }"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-badge :status="getDocStatusBadge(record.status)" :text="getDocumentStatusLabel(record.status)" />
          </template>
          <template v-if="column.key === 'file_size'">
            {{ formatFileSize(record.file_size) }}
          </template>
          <template v-if="column.key === 'chunk_strategy'">
            {{ getChunkStrategyLabel(record.chunk_strategy) }}
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="handlePreview(record)">预览</a-button>
              <a-button type="link" size="small" @click="showChunkPreview(record)">切片预览</a-button>
              <a-popconfirm title="确定删除此文件？" @confirm="handleDelete(record.id)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <!-- 上传弹窗 -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传文件"
      :footer="null"
      :width="560"
      :destroy-on-close="true"
    >
      <!-- 步骤1: 选择知识库和切分策略 -->
      <a-form :model="uploadForm" layout="vertical">
        <a-form-item label="目标知识库" :rules="[{ required: true, message: '请选择知识库' }]">
          <a-select v-model:value="uploadForm.kb_id" placeholder="选择知识库">
            <a-select-option v-for="kb in kbOptions" :key="kb.id" :value="kb.id">
              {{ kb.name }}
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-form-item label="切分策略">
          <a-radio-group v-model:value="uploadForm.chunk_strategy">
            <a-radio-button value="fixed_token">固定Token</a-radio-button>
            <a-radio-button value="semantic">语义切块</a-radio-button>
            <a-radio-button value="paragraph">段落切块</a-radio-button>
            <a-radio-button value="heading_level">标题层级</a-radio-button>
            <a-radio-button value="qa_pair">问答对</a-radio-button>
            <a-radio-button value="recursive">递归切片</a-radio-button>
            <a-radio-button value="ai_assisted">AI辅助</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-form-item label="块大小 (Token)">
          <a-input-number v-model:value="uploadForm.chunk_size" :min="64" :max="4096" style="width:100%" />
        </a-form-item>

        <a-form-item label="重叠大小 (Token)">
          <a-input-number v-model:value="uploadForm.overlap" :min="0" :max="1024" style="width:100%" />
        </a-form-item>

        <a-form-item>
          <!-- 拖拽上传区域 -->
          <a-upload-dragger
            :multiple="false"
            :before-upload="beforeUpload"
            :show-upload-list="false"
            :custom-request="() => {}"
          >
            <p class="ant-upload-drag-icon">
              <InboxOutlined style="font-size:36px;color:var(--brand-500)" />
            </p>
            <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
            <p class="ant-upload-hint">
              支持 PDF、DOCX、PPTX、TXT、MD、CSV、XLSX
            </p>
          </a-upload-dragger>
        </a-form-item>
      </a-form>

      <!-- 上传进度 -->
      <div v-if="uploading" style="margin-top:12px">
        <a-progress :percent="uploadProgress" :status="uploadError ? 'exception' : 'active'" />
        <div class="text-sm text-secondary" style="margin-top:4px">
          {{ uploadStatusText }}
        </div>
      </div>
    </a-modal>

    <!-- 切片预览弹窗 -->
    <a-modal
      v-model:open="chunkPreviewOpen"
      title="切片预览"
      :footer="null"
      :width="900"
      :bodyStyle="{ maxHeight: '70vh', overflowY: 'auto' }"
      @open="fetchChunkPreview"
    >
      <a-table
        :columns="chunkColumns"
        :data-source="chunkList"
        :pagination="{ total: chunkTotal, pageSize: chunkPageSize, showSizeChanger: true, pageSizeOptions: ['10','20','50','100'], onChange: onChunkPageChange, onShowSizeChange: onChunkPageChange }"
        size="small"
        row-key="id"
        :scroll="{ y: 400 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'content'">
            <div class="chunk-content">{{ record.content }}</div>
          </template>
        </template>
      </a-table>
    </a-modal>

    <!-- 文档预览弹窗 -->
    <a-modal
      v-model:open="previewModalOpen"
      :title="`预览: ${previewData?.filename || ''}`"
      :footer="null"
      :width="900"
      :destroy-on-close="true"
    >
      <div v-if="previewLoading" style="text-align:center;padding:40px">
        <a-spin tip="加载中..." />
      </div>
      <div v-else-if="previewData" class="preview-container">
        <!-- PDF预览 -->
        <iframe
          v-if="previewData.type === 'pdf'"
          :src="`data:application/pdf;base64,${previewData.data}`"
          style="width:100%;height:70vh;border:none"
        />
        <!-- HTML预览 (DOCX) -->
        <div
          v-else-if="previewData.type === 'html'"
          class="preview-html"
          v-html="previewData.data"
        />
        <!-- 文本预览 (TXT/MD) -->
        <pre v-else-if="previewData.type === 'text'" class="preview-text">{{ previewData.data }}</pre>
      </div>
      <div v-else style="text-align:center;padding:40px;color:#999">
        无法加载预览
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { UploadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { listDocumentsApi, deleteDocumentApi, uploadDocumentApi, listDocumentChunksApi, previewDocumentApi, type DocumentPreviewResponse } from '@/api/documents'
import { listKBsApi } from '@/api/knowledgeBases'
import type { DocumentInfo, ChunkInfo } from '@/types/document'
import type { KBInfo } from '@/types/knowledgeBase'
import { formatDateTime, formatFileSize, getDocumentStatusLabel, getChunkStrategyLabel } from '@/utils/format'

const route = useRoute()

const loading = ref(false)
const docList = ref<DocumentInfo[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const filterKBId = ref<number | undefined>(undefined)
const filterStatus = ref<string | undefined>(undefined)

const kbOptions = ref<KBInfo[]>([])

const columns = [
  { title: '文件名', dataIndex: 'original_filename', key: 'filename', ellipsis: true },
  { title: '上传人', dataIndex: 'uploader_name', key: 'uploader', width: 100 },
  { title: '大小', key: 'file_size', width: 90 },
  { title: '切分策略', key: 'chunk_strategy', width: 120 },
  { title: '切片数', dataIndex: 'chunk_count', key: 'chunk_count', width: 80, align: 'right' as const },
  { title: '状态', key: 'status', width: 110 },
  { title: '上传时间', key: 'created_at', width: 140 },
  { title: '操作', key: 'action', width: 200, fixed: 'right' as const },
]

async function fetchList() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: currentPage.value, page_size: pageSize.value }
    if (filterKBId.value) params.kb_id = filterKBId.value
    if (filterStatus.value) params.status_filter = filterStatus.value
    const res = await listDocumentsApi(params as any)
    docList.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function fetchKBs() {
  const res = await listKBsApi({ page: 1, page_size: 100 })
  kbOptions.value = res.items
}

function getDocStatusBadge(status: string) {
  const map: Record<string, string> = { completed: 'success', failed: 'error', pending: 'default', parsing: 'processing', embedding: 'processing' }
  return map[status] || 'default'
}

async function handleDelete(docId: number) {
  await deleteDocumentApi(docId)
  message.success('文件已删除')
  await fetchList()
}

// 文档预览
const previewModalOpen = ref(false)
const previewLoading = ref(false)
const previewData = ref<DocumentPreviewResponse | null>(null)

async function handlePreview(doc: DocumentInfo) {
  previewModalOpen.value = true
  previewLoading.value = true
  previewData.value = null
  try {
    previewData.value = await previewDocumentApi(doc.id)
  } catch {
    message.error('预览失败')
  } finally {
    previewLoading.value = false
  }
}

function onPageChange(page: number) {
  currentPage.value = page
  fetchList()
}

// 上传
const showUploadModal = ref(false)
const uploadForm = reactive({ kb_id: null as number | null, chunk_strategy: 'fixed_token', chunk_size: 512, overlap: 128 })

/** 打开上传弹窗时自动填充当前筛选的知识库 */
function openUploadModal() {
  // 优先用当前筛选的kb_id
  const targetKbId = filterKBId.value || (route.query.kb_id ? Number(route.query.kb_id) : null)
  if (targetKbId) {
    uploadForm.kb_id = targetKbId
  } else if (kbOptions.value.length === 1) {
    // 只有1个知识库时直接自动选中
    uploadForm.kb_id = kbOptions.value[0].id
  }
  showUploadModal.value = true
}
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadError = ref(false)
const uploadStatusText = ref('')

function beforeUpload(file: File) {
  if (!uploadForm.kb_id) {
    message.warning('请先选择知识库')
    return false
  }
  doUpload(file)
  return false
}

async function doUpload(file: File) {
  uploading.value = true
  uploadError.value = false
  uploadProgress.value = 0
  uploadStatusText.value = '上传中...'
  try {
    await uploadDocumentApi(uploadForm.kb_id!, file, uploadForm.chunk_strategy, (p) => {
      uploadProgress.value = p
      if (p < 50) uploadStatusText.value = '上传中...'
      else if (p < 80) uploadStatusText.value = '解析中...'
      else uploadStatusText.value = '处理中...'
    })
    message.success('文件上传成功，正在后台处理')
    showUploadModal.value = false
    await fetchList()
  } catch {
    uploadError.value = true
    uploadStatusText.value = '上传失败'
  } finally {
    uploading.value = false
  }
}

// 切片预览
const chunkPreviewOpen = ref(false)
const previewDoc = ref<DocumentInfo | null>(null)
const chunkList = ref<ChunkInfo[]>([])
const chunkTotal = ref(0)
const chunkPageSize = ref(20)

const chunkColumns = [
  { title: '序号', dataIndex: 'chunk_index', key: 'index', width: 60 },
  { title: '内容预览', key: 'content' },
  { title: 'Token', dataIndex: 'token_count', key: 'tokens', width: 80, align: 'right' as const },
]

function showChunkPreview(doc: DocumentInfo) {
  previewDoc.value = doc
  chunkPreviewOpen.value = true
  fetchChunkPreview(1)
}

async function fetchChunkPreview(page = 1, pageSize?: number) {
  if (!previewDoc.value) return
  if (pageSize !== undefined) chunkPageSize.value = pageSize
  const res = await listDocumentChunksApi(previewDoc.value.id, page, chunkPageSize.value)
  chunkList.value = res.chunks
  chunkTotal.value = res.total
}

function onChunkPageChange(page: number, pageSize: number) {
  fetchChunkPreview(page, pageSize)
}

onMounted(async () => {
  await fetchKBs()
  const kbId = route.query.kb_id
  if (kbId) filterKBId.value = Number(kbId)
  await fetchList()
})
</script>

<style scoped>
.chunk-content {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.preview-container {
  min-height: 400px;
}

.preview-html {
  padding: 16px;
  line-height: 1.8;
  font-size: 14px;
}

.preview-html h1,
.preview-html h2,
.preview-html h3 {
  margin: 16px 0 8px;
  font-weight: 600;
}

.preview-html p {
  margin: 8px 0;
}

.preview-text {
  white-space: pre-wrap;
  word-break: break-word;
  padding: 16px;
  background: var(--color-bg-secondary);
  border-radius: 8px;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 60vh;
  overflow-y: auto;
}
</style>
