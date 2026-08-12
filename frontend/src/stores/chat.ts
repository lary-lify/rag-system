/**
 * 对话状态管理 — SSE 流式聊天状态
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ConversationInfo, MessageHistoryItem, SourceChunk } from '@/types/conversation'
import type { KBInfo } from '@/types/knowledgeBase'
import { createChatSSE } from '@/api/conversations'

export interface ChatMessage {
  id: string             // 临时前端ID
  serverId?: number      // 后端 message ID (完成后分配)
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  isStreaming?: boolean  // 是否正在流式输出
  sourceChunks?: SourceChunk[]
  inputTokens?: number
  outputTokens?: number
  totalTokens?: number
}

export const useChatStore = defineStore('chat', () => {
  // 当前对话
  const currentConversationId = ref<number | null>(null)
  const selectedKBIds = ref<number[]>([])
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const abortController = ref<AbortController | null>(null)

  // 是否有活跃的流式对话
  const hasStreaming = computed(() => isStreaming.value)

  /** 添加消息 */
  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  /** 更新最后一条消息内容 (用于流式追加) */
  function appendToLastAssistant(content: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content += content
    }
  }

  /** 设置最后一条消息流式状态 */
  function setLastAssistantStreaming(streaming: boolean) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.isStreaming = streaming
    }
  }

  /** 设置最后一条消息的源 */
  function setLastAssistantSources(chunks: SourceChunk[]) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.sourceChunks = chunks
    }
  }

  /** 设置最后一条消息的 Token 信息 */
  function setLastAssistantTokens(tokens: { message_id?: number; input_tokens: number; output_tokens: number; total_tokens: number }) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      if (tokens.message_id) {
        last.serverId = tokens.message_id
      }
      last.inputTokens = tokens.input_tokens
      last.outputTokens = tokens.output_tokens
      last.totalTokens = tokens.total_tokens
    }
  }

  /** 发送消息并建立 SSE 连接 */
  function sendMessage(question: string, kbIds: number[]) {
    // 添加用户消息
    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: question,
      timestamp: new Date(),
    })

    // 添加空的 assistant 消息占位
    const assistantMsg: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      sourceChunks: [],
    }
    addMessage(assistantMsg)
    isStreaming.value = true

    // 建立 SSE
    const controller = createChatSSE(
      {
        conversation_id: currentConversationId.value,
        question,
        kb_ids: kbIds,
      },
      {
        onConversationId: (id) => {
          currentConversationId.value = id
        },
        onChunk: (content) => {
          appendToLastAssistant(content)
        },
        onSourceChunks: (chunks) => {
          setLastAssistantSources(chunks as SourceChunk[])
        },
        onDone: (data) => {
          setLastAssistantTokens(data)
          setLastAssistantStreaming(false)
          isStreaming.value = false
          abortController.value = null
        },
        onError: (error) => {
          appendToLastAssistant(`\n\n[错误] ${error}`)
          setLastAssistantStreaming(false)
          isStreaming.value = false
          abortController.value = null
        },
      }
    )

    abortController.value = controller
  }

  /** 停止生成 */
  function stopGeneration() {
    if (abortController.value) {
      abortController.value.abort()
      setLastAssistantStreaming(false)
      isStreaming.value = false
      abortController.value = null
    }
  }

  /** 加载历史消息到界面 */
  function loadHistory(historyMsgs: MessageHistoryItem[]) {
    messages.value = historyMsgs.flatMap((msg) => [
      {
        id: `user-hist-${msg.id}`,
        serverId: msg.id,
        role: 'user' as const,
        content: msg.question,
        timestamp: new Date(msg.created_at),
      },
      {
        id: `assistant-hist-${msg.id}`,
        serverId: msg.id,
        role: 'assistant' as const,
        content: msg.answer,
        timestamp: new Date(msg.created_at),
        sourceChunks: msg.source_chunks,
        inputTokens: msg.input_tokens,
        outputTokens: msg.output_tokens,
        totalTokens: msg.input_tokens + msg.output_tokens,
      },
    ])
  }

  /** 新建对话重置状态 */
  function resetChat() {
    currentConversationId.value = null
    messages.value = []
    isStreaming.value = false
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
  }

  return {
    currentConversationId,
    selectedKBIds,
    messages,
    isStreaming,
    hasStreaming,
    addMessage,
    appendToLastAssistant,
    setLastAssistantStreaming,
    setLastAssistantSources,
    setLastAssistantTokens,
    sendMessage,
    stopGeneration,
    loadHistory,
    resetChat,
  }
})
