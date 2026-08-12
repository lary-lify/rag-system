<template>
  <div class="chat-page">
    <!-- 左侧知识库选择面板 -->
    <div class="chat-sidebar">
      <div class="chat-sidebar-header">
        <span class="font-semibold">知识库选择</span>
        <a-button size="small" type="link" @click="toggleAllKBs">
          {{ allSelected ? '取消全选' : '全选' }}
        </a-button>
      </div>
      <div class="kb-tree">
        <div v-if="kbLoading" style="text-align:center;padding:var(--space-6)">
          <a-spin size="small" />
        </div>
        <a-checkbox-group v-model:value="selectedKBIds" style="width:100%">
          <div
            v-for="kb in kbOptions"
            :key="kb.id"
            class="kb-checkbox-item"
          >
            <a-checkbox :value="kb.id">
              <span class="kb-checkbox-name">{{ kb.name }}</span>
            </a-checkbox>
            <span class="kb-checkbox-count">{{ kb.doc_count }} 文档</span>
          </div>
        </a-checkbox-group>
      </div>

      <!-- 对话历史列表 -->
      <div class="conv-history">
        <div class="chat-sidebar-header">
          <span class="font-semibold">对话历史</span>
          <a-button size="small" type="link" @click="newConversation">新对话</a-button>
        </div>
        <div class="conv-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            :class="['conv-item', { active: conv.id === chatStore.currentConversationId }]"
            @click="switchConversation(conv)"
          >
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-meta">
              <span>{{ conv.message_count }} 轮</span>
              <a-popconfirm title="删除此对话？" @confirm="handleDeleteConv(conv.id)">
                <DeleteOutlined class="conv-delete" @click.stop />
              </a-popconfirm>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 对话主区域 -->
    <div class="chat-main">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="messagesContainer">
        <div v-if="chatStore.messages.length === 0" class="empty-state">
          <div class="empty-state-icon">💬</div>
          <div class="empty-state-text">选择知识库，输入问题开始对话</div>
        </div>

        <div
          v-for="msg in chatStore.messages"
          :key="msg.id"
          :class="['chat-message', msg.role === 'user' ? 'chat-message-right' : 'chat-message-left']"
        >
          <div :class="msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant'" class="chat-bubble">
            <!-- 用户消息 -->
            <template v-if="msg.role === 'user'">
              {{ msg.content }}
            </template>

            <!-- AI 消息 -->
            <template v-else>
              <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>

              <!-- 流式输出中 -->
              <span v-if="msg.isStreaming" class="typing-cursor">|</span>

              <!-- Token 信息 (仅管理员可见) -->
              <div v-if="authStore.isDeptAdminOrAbove && msg.totalTokens && !msg.isStreaming" class="msg-token-info">
                <span>输入: {{ msg.inputTokens }} | 输出: {{ msg.outputTokens }} | 总计: {{ msg.totalTokens }}</span>
                <span style="margin-left:8px;color:var(--brand-600)">
                  预估费用: {{ formatCost(calcChatCost(msg.inputTokens || 0, msg.outputTokens || 0)) }}
                </span>
              </div>

              <!-- 反馈按钮 -->
              <div v-if="!msg.isStreaming && msg.serverId" class="msg-feedback">
                <span class="feedback-label">这个回答有帮助吗？</span>
                <div class="feedback-icons">
                  <span
                    :class="['feedback-icon', 'like-icon', { active: msg.feedback === 1 }]"
                    @click="handleFeedback(msg, 1)"
                    title="有用"
                  >
                    <LikeOutlined />
                  </span>
                  <span
                    :class="['feedback-icon', 'dislike-icon', { active: msg.feedback === 0 }]"
                    @click="handleFeedback(msg, 0)"
                    title="无用"
                  >
                    <DislikeOutlined />
                  </span>
                </div>
              </div>

              <!-- 追问建议 -->
              <div v-if="!msg.isStreaming && msg.sourceChunks && msg.sourceChunks.length > 0 && getFollowUpSuggestions(msg).length > 0" class="follow-up-section">
                <div class="follow-up-header">
                  <span class="follow-up-icon">💡</span>
                  <span class="follow-up-title">你可能还想问</span>
                </div>
                <div class="follow-up-list">
                  <div
                    v-for="(suggestion, idx) in getFollowUpSuggestions(msg)"
                    :key="idx"
                    class="follow-up-item"
                    @click="handleFollowUp(suggestion)"
                  >
                    <span class="follow-up-text">{{ suggestion }}</span>
                    <span class="follow-up-arrow">→</span>
                  </div>
                </div>
              </div>

              <!-- 溯源来源 -->
              <div v-if="msg.sourceChunks && msg.sourceChunks.length > 0 && !msg.isStreaming" class="source-panel">
                <a-collapse :bordered="false">
                  <a-collapse-panel :key="'1'">
                    <template #header>📎 来源引用 ({{ msg.sourceChunks.length }} 处)</template>
                    <div
                      v-for="(chunk, idx) in msg.sourceChunks"
                      :key="idx"
                      class="source-item"
                    >
                      <div class="source-item-header">
                        <FileOutlined />
                        <span>{{ chunk.document_name || '未知文档' }}</span>
                        <a-tag size="small" color="blue">相似度: {{ (chunk.score * 100).toFixed(1) }}%</a-tag>
                      </div>
                      <div class="source-item-content">{{ chunk.content }}</div>
                    </div>
                  </a-collapse-panel>
                </a-collapse>
              </div>
            </template>
          </div>
        </div>

        <!-- 打字指示器 -->
        <div v-if="chatStore.hasStreaming && streamingPlaceholder" class="chat-message chat-message-left">
          <div class="chat-bubble chat-bubble-assistant">
            <div class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <!-- 停止生成按钮 -->
        <div v-if="chatStore.hasStreaming" class="stop-btn-wrapper">
          <a-button danger class="stop-breathing" @click="chatStore.stopGeneration()">
            <PauseCircleOutlined /> 停止生成
          </a-button>
        </div>

        <div class="chat-input-row">
          <a-textarea
            v-model:value="inputQuestion"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            placeholder="输入问题，基于知识库智能回答..."
            :disabled="chatStore.hasStreaming"
            @keydown.enter.exact.prevent="handleSend"
          />
          <a-button
            type="primary"
            shape="circle"
            size="large"
            :disabled="!inputQuestion.trim() || selectedKBIds.length === 0 || chatStore.hasStreaming"
            :loading="chatStore.hasStreaming"
            @click="handleSend"
          >
            <SendOutlined />
          </a-button>
        </div>
        <div v-if="selectedKBIds.length === 0" class="text-xs text-warning" style="margin-top:4px">
          请选择至少一个知识库
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { SendOutlined, PauseCircleOutlined, FileOutlined, DeleteOutlined, LikeOutlined, DislikeOutlined } from '@ant-design/icons-vue'
import { marked } from 'marked'
import { useChatStore } from '@/stores/chat'
import { listKBsApi } from '@/api/knowledgeBases'
import { listConversationsApi, getMessagesApi, deleteConversationApi, setFeedbackApi } from '@/api/conversations'
import type { KBInfo } from '@/types/knowledgeBase'
import type { ConversationInfo, MessageHistoryItem } from '@/types/conversation'
import { useCost } from '@/composables/useCost'
import { useAuthStore } from '@/stores/auth'

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked.parse(text) as string
}

const chatStore = useChatStore()
const authStore = useAuthStore()
const { formatCost, calcChatCost, fetchPricing } = useCost()

const messagesContainer = ref<HTMLElement | null>(null)
const inputQuestion = ref('')
const streamingPlaceholder = ref(false)

const kbOptions = ref<KBInfo[]>([])
const kbLoading = ref(false)
const selectedKBIds = ref<number[]>([])
const conversations = ref<ConversationInfo[]>([])

const allSelected = computed(() =>
  kbOptions.value.length > 0 && selectedKBIds.value.length === kbOptions.value.length
)

async function fetchKBs() {
  kbLoading.value = true
  try {
    const res = await listKBsApi({ page: 1, page_size: 100 })
    kbOptions.value = res.items
  } finally {
    kbLoading.value = false
  }
}

function toggleAllKBs() {
  if (allSelected.value) {
    selectedKBIds.value = []
  } else {
    selectedKBIds.value = kbOptions.value.map((kb) => kb.id)
  }
}

async function fetchConversations() {
  try {
    const res = await listConversationsApi({ page: 1, page_size: 50 })
    conversations.value = res.items
  } catch { /* empty */ }
}

async function switchConversation(conv: ConversationInfo) {
  chatStore.resetChat()
  chatStore.currentConversationId = conv.id
  selectedKBIds.value = conv.kb_ids || []
  inputQuestion.value = '' // 清空输入框

  try {
    const msgs = await getMessagesApi(conv.id, { page: 1, page_size: 100 })
    chatStore.loadHistory(msgs)
    await nextTick()
    scrollToBottom()
  } catch { /* empty */ }
}

function newConversation() {
  chatStore.resetChat()
  selectedKBIds.value = []
  inputQuestion.value = '' // 清空输入框
}

async function handleDeleteConv(convId: number) {
  await deleteConversationApi(convId)
  message.success('对话已删除')
  if (chatStore.currentConversationId === convId) {
    newConversation()
  }
  await fetchConversations()
}

function handleSend() {
  const question = inputQuestion.value.trim()
  if (!question || selectedKBIds.value.length === 0) return

  inputQuestion.value = ''
  streamingPlaceholder.value = true

  chatStore.sendMessage(question, selectedKBIds.value)

  nextTick(() => {
    scrollToBottom()
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 监听消息变化自动滚动
watch(
  () => chatStore.messages.length,
  () => scrollToBottom()
)

// 监听流式内容变化
watch(
  () => chatStore.messages[chatStore.messages.length - 1]?.content,
  () => {
    if (chatStore.hasStreaming) scrollToBottom()
  }
)

// 监听流式结束
watch(
  () => chatStore.hasStreaming,
  (val) => {
    if (!val) {
      streamingPlaceholder.value = false
      fetchConversations()
    }
  }
)

// 反馈处理
async function handleFeedback(msg: any, value: number) {
  const currentConvId = chatStore.currentConversationId
  const msgId = msg.serverId || msg.id

  if (!currentConvId || !msgId) {
    message.warning('无法提交反馈，请重试')
    return
  }

  // 检查msgId是否为数字
  const numericMsgId = Number(msgId)
  if (isNaN(numericMsgId)) {
    message.warning('消息ID无效')
    return
  }

  try {
    console.log('[Feedback] Sending:', { convId: currentConvId, msgId: numericMsgId, feedback: value })
    await setFeedbackApi(currentConvId, numericMsgId, value)
    msg.feedback = value
    message.success(value === 1 ? '感谢您的反馈！' : '已记录，我们会继续优化')
  } catch (err: any) {
    console.error('[Feedback Error]', err)
    const errorMsg = err?.response?.data?.detail || err?.message || '未知错误'
    message.error(`反馈失败: ${JSON.stringify(errorMsg)}`)
  }
}

// 追问建议
function getFollowUpSuggestions(msg: any): string[] {
  const suggestions: string[] = []
  const content = msg.content || ''

  // 基于内容生成追问建议
  if (content.includes('续航') || content.includes('电池')) {
    suggestions.push('充电方式是什么？')
    suggestions.push('省电模式怎么设置？')
  }
  if (content.includes('防水') || content.includes('水')) {
    suggestions.push('可以戴着游泳吗？')
    suggestions.push('防水等级是多少？')
  }
  if (content.includes('运动') || content.includes('健身')) {
    suggestions.push('支持哪些运动模式？')
    suggestions.push('运动数据怎么同步？')
  }
  if (content.includes('配对') || content.includes('连接')) {
    suggestions.push('连接失败怎么办？')
    suggestions.push('支持哪些手机？')
  }

  // 如果没有特定建议，提供通用追问
  if (suggestions.length === 0) {
    suggestions.push('详细介绍一下')
    suggestions.push('还有其他功能吗？')
  }

  return suggestions.slice(0, 3)
}

function handleFollowUp(question: string) {
  inputQuestion.value = question
  handleSend()
}

onMounted(async () => {
  await fetchPricing()
  await fetchKBs()
  await fetchConversations()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - var(--topbar-height));
  overflow: hidden;
}

/* 左侧面板 */
.chat-sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--color-bg-container);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border-secondary);
  font-size: var(--text-sm);
}

.kb-tree {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2) 0;
}

.kb-checkbox-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.kb-checkbox-item:hover {
  background: var(--color-bg-hover);
}

.kb-checkbox-name {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  margin-left: var(--space-2);
}

.kb-checkbox-count {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.conv-history {
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  max-height: 40%;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
}

.conv-item {
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
  border-bottom: 1px solid var(--color-border-secondary);
}

.conv-item:hover,
.conv-item.active {
  background: var(--color-bg-hover);
}

.conv-title {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

.conv-delete {
  font-size: 12px;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.conv-item:hover .conv-delete {
  opacity: 1;
}

/* 主对话区 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--color-bg-page);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

.chat-message {
  margin-bottom: var(--space-4);
  display: flex;
}

.chat-message-right {
  justify-content: flex-end;
}

.chat-message-left {
  justify-content: flex-start;
}

.typing-cursor {
  animation: blink 1s infinite;
  color: var(--brand-500);
  font-weight: bold;
}

@keyframes blink {
  0%, 50% { opacity: 1 }
  51%, 100% { opacity: 0 }
}

.msg-token-info {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border-secondary);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.msg-feedback {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border-secondary);
}

.feedback-label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.feedback-icons {
  display: flex;
  gap: 8px;
}

.feedback-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
}

.like-icon {
  color: #9ca3af;
}

.like-icon:hover,
.like-icon.active {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.dislike-icon {
  color: #9ca3af;
}

.dislike-icon:hover,
.dislike-icon.active {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.follow-up-section {
  margin-top: var(--space-3);
  padding: var(--space-3);
  background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%);
  border-radius: 12px;
  border: 1px solid #e8ecff;
}

.follow-up-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: var(--space-2);
}

.follow-up-icon {
  font-size: 14px;
}

.follow-up-title {
  font-size: 13px;
  font-weight: 500;
  color: #4a5568;
}

.follow-up-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.follow-up-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: white;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.follow-up-item:hover {
  border-color: var(--brand-400);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
  transform: translateX(4px);
}

.follow-up-text {
  font-size: 13px;
  color: #374151;
}

.follow-up-arrow {
  font-size: 12px;
  color: #9ca3af;
  transition: color 0.2s;
}

.follow-up-item:hover .follow-up-arrow {
  color: var(--brand-500);
}

.source-panel {
  margin-top: var(--space-3);
}

.source-item {
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border-secondary);
}

.source-item:last-child {
  border-bottom: none;
}

.source-item-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-1);
}

.source-item-content {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  line-height: 1.5;
  padding: var(--space-2);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 输入区 */
.chat-input-area {
  padding: var(--space-4) var(--space-6);
  background: var(--color-bg-container);
  border-top: 1px solid var(--color-border);
}

.stop-btn-wrapper {
  text-align: center;
  margin-bottom: var(--space-2);
}

.chat-input-row {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
}

.chat-input-row :deep(.ant-input) {
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-base);
}

/* Markdown rendered content */
.msg-content {
  word-break: break-word;
}
.msg-content :deep(p) {
  margin: 0 0 8px;
}
.msg-content :deep(p:last-child) {
  margin-bottom: 0;
}
.msg-content :deep(ul), .msg-content :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.msg-content :deep(li) {
  margin: 2px 0;
}
.msg-content :deep(code) {
  background: var(--color-bg-secondary);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 0.9em;
}
.msg-content :deep(pre) {
  background: var(--color-bg-secondary);
  padding: 8px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}
.msg-content :deep(pre code) {
  background: none;
  padding: 0;
}
.msg-content :deep(strong) {
  font-weight: 600;
}
.msg-content :deep(blockquote) {
  border-left: 3px solid var(--brand-400);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--color-text-secondary);
}
</style>
