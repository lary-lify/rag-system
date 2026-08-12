/**
 * 通用格式化工具函数
 */
import dayjs from 'dayjs'

/** 格式化日期时间 */
export function formatDateTime(date: string | Date, format: string = 'YYYY-MM-DD HH:mm:ss'): string {
  return dayjs(date).format(format)
}

/** 格式化文件大小 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + units[i]
}

/** 格式化数字 (千位分隔) */
export function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN')
}

/** 切分策略名称映射 */
export function getChunkStrategyLabel(strategy: string): string {
  const map: Record<string, string> = {
    fixed_token: '固定Token切块',
    semantic: '语义切块',
    paragraph: '段落切块',
    heading_level: '标题层级切块',
    qa_pair: '问答对切块',
    recursive: '递归切块',
    ai_assisted: 'AI辅助切块',
  }
  return map[strategy] || strategy
}

/** 文档状态标签映射 */
export function getDocumentStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待处理',
    parsing: '解析中',
    embedding: '向量化中',
    completed: '入库成功',
    failed: '入库失败',
  }
  return map[status] || status
}

/** 文档状态颜色 */
export function getDocumentStatusColor(status: string): string {
  const map: Record<string, string> = {
    pending: 'default',
    parsing: 'processing',
    embedding: 'processing',
    completed: 'success',
    failed: 'error',
  }
  return map[status] || 'default'
}

/** 角色标签映射 */
export function getRoleLabel(role: string): string {
  const map: Record<string, string> = {
    super_admin: '超级管理员',
    dept_admin: '部门管理员',
    user: '普通用户',
  }
  return map[role] || role
}

/** 角色颜色 */
export function getRoleColor(role: string): string {
  const map: Record<string, string> = {
    super_admin: 'red',
    dept_admin: 'blue',
    user: 'default',
  }
  return map[role] || 'default'
}

/** 用户状态标签 */
export function getUserStatusLabel(status: string): string {
  return status === 'active' ? '已启用' : '已禁用'
}

/** 用户状态颜色 */
export function getUserStatusColor(status: string): string {
  return status === 'active' ? 'success' : 'error'
}
