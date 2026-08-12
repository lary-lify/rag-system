/**
 * 对话 API (含 SSE 流式)
 */
import request from './index'
import type {
  ConversationInfo, ConversationListResponse,
  ConversationCreateRequest, ConversationUpdateRequest,
  ChatRequest, MessageHistoryItem,
} from '@/types/conversation'

/** 创建对话 */
export function createConversationApi(data: ConversationCreateRequest): Promise<{ id: number }> {
  return request.post('/conversations', data)
}

/** 对话列表 */
export function listConversationsApi(params: { page: number; page_size: number }): Promise<ConversationListResponse> {
  return request.get('/conversations', { params })
}

/** 对话详情 */
export function getConversationApi(convId: number): Promise<ConversationInfo> {
  return request.get(`/conversations/${convId}`)
}

/** 更新对话 */
export function updateConversationApi(convId: number, data: ConversationUpdateRequest): Promise<{ detail: string }> {
  return request.put(`/conversations/${convId}`, data)
}

/** 删除对话 */
export function deleteConversationApi(convId: number): Promise<{ detail: string }> {
  return request.delete(`/conversations/${convId}`)
}

/** 获取消息历史 */
export function getMessagesApi(
  convId: number,
  params: { page: number; page_size: number }
): Promise<MessageHistoryItem[]> {
  return request.get(`/conversations/${convId}/messages`, { params })
}

/** 设置消息反馈 (1=good, 0=bad) */
export function setFeedbackApi(
  convId: number,
  msgId: number,
  feedback: number
): Promise<{ detail: string; feedback: number }> {
  return request.post(`/conversations/${convId}/messages/${msgId}/feedback`, { feedback })
}

/**
 * 创建 SSE 流式对话连接
 * 使用 fetch + ReadableStream 而非 EventSource，因为 EventSource 不支持 POST
 * 返回 AbortController 用于停止生成
 */
export function createChatSSE(
  data: ChatRequest,
  callbacks: {
    onConversationId?: (id: number) => void
    onChunk?: (content: string) => void
    onSourceChunks?: (chunks: unknown[]) => void
    onDone?: (data: { message_id: number; input_tokens: number; output_tokens: number; total_tokens: number }) => void
    onError?: (error: string) => void
  }
): AbortController {
  const controller = new AbortController()
  const token = localStorage.getItem('access_token')
  // SSE 直连后端，绕过 Vite 代理缓冲
  const baseURL = 'http://localhost:8000/api'

  fetch(`${baseURL}/conversations/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: 'SSE connection failed' }))
      callbacks.onError?.(errData.detail || 'SSE 连接失败')
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      callbacks.onError?.('Stream reader not available')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        // Keep last partial line in buffer
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue

          try {
            const eventData = JSON.parse(trimmed.substring(6))

            switch (eventData.type) {
              case 'conversation_id':
                callbacks.onConversationId?.(eventData.value)
                break
              case 'chunk':
                callbacks.onChunk?.(eventData.content)
                // Small delay for typewriter effect when tokens arrive in bursts
                await new Promise(r => setTimeout(r, 20))
                break
              case 'source_chunks':
                callbacks.onSourceChunks?.(eventData.chunks)
                break
              case 'done':
                callbacks.onDone?.(eventData)
                break
              case 'error':
                callbacks.onError?.(eventData.detail)
                break
            }
          } catch {
            // skip unparseable lines
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        callbacks.onError?.(err.message || 'SSE stream error')
      }
    }
  }).catch((err: Error) => {
    if (err.name !== 'AbortError') {
      callbacks.onError?.(err.message || 'SSE request failed')
    }
  })

  return controller
}
