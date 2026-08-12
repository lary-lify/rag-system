/**
 * 费用计算工具组合式函数
 * 前端从环境变量（由后端 /api/config 下发）读取单价，做本地计算
 */
import { ref, onMounted } from 'vue'
import { getConfigViewApi } from '@/api/config'

export function useCost() {
  const embeddingPrice = ref(0.0008)
  const deepseekInputPrice = ref(0.001)
  const deepseekOutputPrice = ref(0.002)

  /** 从后端获取计费单价 */
  async function fetchPricing() {
    try {
      const config = await getConfigViewApi()
      for (const item of config.config_items) {
        if (item.key === 'TONGYI_EMBEDDING_TOKEN_PRICE') {
          embeddingPrice.value = parseFloat(item.value) || 0.0008
        } else if (item.key === 'DEEPSEEK_INPUT_TOKEN_PRICE') {
          deepseekInputPrice.value = parseFloat(item.value) || 0.001
        } else if (item.key === 'DEEPSEEK_OUTPUT_TOKEN_PRICE') {
          deepseekOutputPrice.value = parseFloat(item.value) || 0.002
        }
      }
    } catch {
      // 使用默认值
    }
  }

  /** 计算向量预估费用 */
  function calcEmbeddingCost(tokens: number): number {
    return Math.round(tokens * embeddingPrice.value * 10000) / 10000
  }

  /** 计算对话预估费用 */
  function calcChatCost(inputTokens: number, outputTokens: number): number {
    const cost =
      inputTokens * deepseekInputPrice.value +
      outputTokens * deepseekOutputPrice.value
    return Math.round(cost * 10000) / 10000
  }

  /** 格式化费用显示 */
  function formatCost(cost: number): string {
    if (cost < 0.01) {
      return `¥${cost.toFixed(6)}`
    }
    return `¥${cost.toFixed(4)}`
  }

  return {
    embeddingPrice,
    deepseekInputPrice,
    deepseekOutputPrice,
    fetchPricing,
    calcEmbeddingCost,
    calcChatCost,
    formatCost,
  }
}
