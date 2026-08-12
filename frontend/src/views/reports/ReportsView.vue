<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">统计报表</h1>
      <div class="filter-bar">
        <!-- 快捷筛选标签 -->
        <div class="filter-tags">
          <a-tag
            v-for="item in filterOptions"
            :key="item.value"
            :color="quickFilter === item.value ? 'blue' : ''"
            class="filter-tag"
            @click="handleFilterClick(item.value)"
          >
            {{ item.label }}
          </a-tag>
        </div>
        <!-- 自定义日期范围 -->
        <a-range-picker
          v-if="quickFilter === 'custom'"
          v-model:value="dateRange"
          :placeholder="['开始', '结束']"
          size="small"
          @change="fetchData"
          style="width: 240px"
        />
        <a-button @click="exportReport" size="small">
          <DownloadOutlined /> 导出
        </a-button>
      </div>
    </div>

    <a-tabs v-model:activeKey="activeTab" @change="fetchData">
      <a-tab-pane key="global" tab="全局总报表" v-if="isSuperAdmin()" />
      <a-tab-pane key="kb" tab="知识库维度" />
      <a-tab-pane key="user" tab="用户维度" />
      <a-tab-pane key="qa" tab="问答统计" />
    </a-tabs>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-card-label">向量总 Token</div>
        <div class="stat-card-value">{{ formatNumber(summary.total_embedding_tokens) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">对话输入 Token</div>
        <div class="stat-card-value">{{ formatNumber(summary.total_chat_input_tokens) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">对话输出 Token</div>
        <div class="stat-card-value">{{ formatNumber(summary.total_chat_output_tokens) }}</div>
      </div>
      <div class="stat-card" style="border-left:3px solid var(--brand-600)">
        <div class="stat-card-label">预估总费用</div>
        <div class="stat-card-value" style="color:var(--brand-600)">{{ formatCost(summary.total_estimated_cost) }}</div>
      </div>
    </div>

    <!-- 问答统计卡片 -->
    <div v-if="activeTab === 'qa'" class="stat-grid">
      <div class="stat-card">
        <div class="stat-card-label">总问答数</div>
        <div class="stat-card-value">{{ qaStats.total_messages }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">反馈率</div>
        <div class="stat-card-value">{{ qaStats.feedback_stats?.feedback_rate || 0 }}%</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">满意率</div>
        <div class="stat-card-value" style="color:var(--success-600)">{{ qaStats.feedback_stats?.satisfaction_rate || 0 }}%</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">检索命中率</div>
        <div class="stat-card-value" style="color:var(--brand-600)">{{ qaStats.hit_rate || 0 }}%</div>
      </div>
    </div>

    <!-- 趋势图 -->
    <div class="card" style="margin-bottom:var(--space-6)">
      <div class="card-header">费用 & 调用量趋势</div>
      <div class="card-body">
        <div ref="trendChartRef" style="height:340px"></div>
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <div class="card-header">
        {{ activeTab === 'kb' ? '知识库费用排行' : activeTab === 'user' ? '用户费用排行' : '每日费用明细' }}
      </div>
      <div class="card-body" style="padding:0">
        <!-- 全局：每日明细 -->
        <a-table
          v-if="activeTab === 'global' && isSuperAdmin()"
          :columns="dayColumns"
          :data-source="summary.by_day"
          :pagination="{ pageSize: 30 }"
          size="small"
          row-key="date"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'embedding_cost'">{{ formatCost(record.embedding_cost) }}</template>
            <template v-if="column.key === 'chat_cost'">{{ formatCost(record.chat_cost) }}</template>
            <template v-if="column.key === 'total_cost'">{{ formatCost(record.total_cost) }}</template>
          </template>
        </a-table>

        <!-- 知识库维度 -->
        <a-table
          v-if="activeTab === 'kb'"
          :columns="kbTableColumns"
          :data-source="summary.by_kb"
          :pagination="{ pageSize: 20 }"
          size="small"
          row-key="kb_id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'cost'">{{ formatCost(record.cost) }}</template>
            <template v-if="column.key === 'tokens'">{{ formatNumber(record.tokens) }}</template>
          </template>
        </a-table>

        <!-- 用户维度 -->
        <a-table
          v-if="activeTab === 'user'"
          :columns="userTableColumns"
          :data-source="summary.by_user"
          :pagination="{ pageSize: 20 }"
          size="small"
          row-key="user_id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'cost'">{{ formatCost(record.cost) }}</template>
            <template v-if="column.key === 'tokens'">{{ formatNumber(record.tokens) }}</template>
          </template>
        </a-table>

        <!-- 问答统计 -->
        <div v-if="activeTab === 'qa'" style="padding:16px">
          <h3 style="margin-bottom:16px">热门问题 TOP 10</h3>
          <a-table
            :columns="[
              { title: '排名', key: 'rank', width: 60 },
              { title: '问题', dataIndex: 'question', key: 'question' },
              { title: '次数', dataIndex: 'count', key: 'count', width: 80, align: 'right' },
            ]"
            :data-source="qaStats.top_questions?.map((q, i) => ({ ...q, rank: i + 1 }))"
            :pagination="false"
            size="small"
            row-key="rank"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'rank'">
                <a-tag :color="record.rank <= 3 ? 'red' : 'default'">{{ record.rank }}</a-tag>
              </template>
            </template>
          </a-table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { getCostSummaryApi, getUsageTrendApi } from '@/api/reports'
import type { CostSummaryResponse, UsageTrendResponse } from '@/types/report'
import { formatNumber } from '@/utils/format'
import { useCost } from '@/composables/useCost'
import { useExport } from '@/composables/useExport'
import { usePermission } from '@/composables/usePermission'

const { formatCost, fetchPricing } = useCost()
const { exportToExcel } = useExport()
const { isSuperAdmin } = usePermission()

const activeTab = ref('global')
const quickFilter = ref<string>('month')
const dateRange = ref<any>(null)
const trendChartRef = ref<HTMLDivElement | null>(null)
let trendChart: echarts.ECharts | null = null

// 筛选选项
const filterOptions = [
  { label: '今天', value: 'today' },
  { label: '本周', value: 'week' },
  { label: '本月', value: 'month' },
  { label: '本季度', value: 'quarter' },
  { label: '今年', value: 'year' },
  { label: '自定义', value: 'custom' },
]

// 筛选切换
function handleFilterClick(value: string) {
  quickFilter.value = value
  fetchData()
}

const summary = reactive<CostSummaryResponse>({
  period_start: '', period_end: '',
  total_embedding_tokens: 0, total_chat_input_tokens: 0,
  total_chat_output_tokens: 0, total_estimated_cost: 0,
  by_user: [], by_kb: [], by_day: [],
})

// Q&A Stats
const qaStats = reactive({
  total_messages: 0,
  feedback_stats: { total: 0, good: 0, bad: 0, feedback_rate: 0, satisfaction_rate: 0 },
  hit_rate: 0,
  top_questions: [] as { question: string; count: number }[],
})

const dayColumns = [
  { title: '日期', dataIndex: 'date', key: 'date', width: 120 },
  { title: '向量费用', key: 'embedding_cost', align: 'right' as const },
  { title: '对话费用', key: 'chat_cost', align: 'right' as const },
  { title: '总费用', key: 'total_cost', align: 'right' as const },
]
const kbTableColumns = [
  { title: '知识库', dataIndex: 'kb_name', key: 'kb_name' },
  { title: 'Token', key: 'tokens', align: 'right' as const },
  { title: '预估费用', key: 'cost', align: 'right' as const },
]
const userTableColumns = [
  { title: '用户', dataIndex: 'username', key: 'username' },
  { title: 'Token', key: 'tokens', align: 'right' as const },
  { title: '预估费用', key: 'cost', align: 'right' as const },
]

// 根据快捷筛选获取日期范围
function getDateRangeByFilter(filter: string): { start_date?: string; end_date?: string } {
  const today = dayjs()

  switch (filter) {
    case 'today':
      return {
        start_date: today.format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'week':
      // 本周一到今天
      const weekStart = today.startOf('week').add(1, 'day') // 周一
      return {
        start_date: weekStart.format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'month':
      // 本月1号到今天
      return {
        start_date: today.startOf('month').format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'quarter':
      // 本季度第一天到今天
      const quarterStart = today.startOf('quarter')
      return {
        start_date: quarterStart.format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'year':
      // 今年1月1号到今天
      return {
        start_date: today.startOf('year').format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'custom':
      if (dateRange.value && dateRange.value[0]) {
        return {
          start_date: dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
          end_date: dayjs(dateRange.value[1]).format('YYYY-MM-DD'),
        }
      }
      return {}
    default:
      return {}
  }
}

// 快捷筛选切换
function handleQuickFilter() {
  fetchData()
}

async function fetchData() {
  const dateParams = getDateRangeByFilter(quickFilter.value)
  const params: Record<string, string> = { ...dateParams }

  // 获取费用汇总
  try {
    const res = await getCostSummaryApi(params)
    Object.assign(summary, res)
  } catch { /* empty */ }

  // 获取趋势数据
  try {
    const trend = await getUsageTrendApi(90, params.start_date, params.end_date)
    renderChart(trend)
  } catch { /* empty */ }

  // 获取问答统计
  if (activeTab.value === 'qa') {
    try {
      const res = await fetch('/api/reports/qa-stats?' + new URLSearchParams(params), {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      }).then(r => r.json())
      Object.assign(qaStats, res)
    } catch { /* empty */ }
  }
}

function renderChart(data: UsageTrendResponse) {
  if (!trendChartRef.value) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)

  // 根据数据量动态调整柱状图宽度
  const dataLength = data.dates.length
  const barWidth = dataLength > 30 ? 6 : dataLength > 15 ? 12 : dataLength > 7 ? 18 : 24

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e5e7eb',
      textStyle: { color: '#374151', fontSize: 12 },
    },
    legend: { data: ['嵌入Token', '对话Token', '费用(¥)'], bottom: 0, textStyle: { fontSize: 12 } },
    grid: { left: 50, right: 60, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLabel: {
        formatter: (v: string) => dayjs(v).format('MM-DD'),
        rotate: dataLength > 15 ? 45 : 0,
        fontSize: 11,
      },
      axisTick: { alignWithLabel: true },
    },
    yAxis: [
      { type: 'value', name: 'Token', nameTextStyle: { fontSize: 11 } },
      { type: 'value', name: '费用 ¥', nameTextStyle: { fontSize: 11 } },
    ],
    series: [
      {
        name: '嵌入Token',
        type: 'bar',
        stack: 'tokens',
        data: data.embedding_tokens,
        barWidth: barWidth,
        itemStyle: { color: '#3b82f6', borderRadius: [2, 2, 0, 0] },
      },
      {
        name: '对话Token',
        type: 'bar',
        stack: 'tokens',
        data: data.chat_input_tokens.map((v, i) => v + data.chat_output_tokens[i]),
        barWidth: barWidth,
        itemStyle: { color: '#22c55e', borderRadius: [2, 2, 0, 0] },
      },
      {
        name: '费用(¥)',
        type: 'line',
        yAxisIndex: 1,
        data: data.costs,
        itemStyle: { color: '#ef4444' },
        symbol: 'circle',
        symbolSize: dataLength > 30 ? 4 : 6,
        lineStyle: { width: 2 },
      },
    ],
  })
}

function exportReport() {
  if (activeTab.value === 'user') {
    exportToExcel(
      summary.by_user.map(u => ({ ...u, cost: formatCost(u.cost), tokens: formatNumber(u.tokens) })),
      [{ header: '用户', key: 'username' }, { header: 'Token', key: 'tokens' }, { header: '预估费用', key: 'cost' }],
      '用户维度费用报表'
    )
  } else if (activeTab.value === 'kb') {
    exportToExcel(
      summary.by_kb.map(k => ({ ...k, cost: formatCost(k.cost), tokens: formatNumber(k.tokens) })),
      [{ header: '知识库', key: 'kb_name' }, { header: 'Token', key: 'tokens' }, { header: '预估费用', key: 'cost' }],
      '知识库维度费用报表'
    )
  } else if (activeTab.value === 'global') {
    exportToExcel(
      summary.by_day.map(d => ({ ...d, embedding_cost: formatCost(d.embedding_cost), chat_cost: formatCost(d.chat_cost), total_cost: formatCost(d.total_cost) })),
      [{ header: '日期', key: 'date' }, { header: '向量费用', key: 'embedding_cost' }, { header: '对话费用', key: 'chat_cost' }, { header: '总费用', key: 'total_cost' }],
      '每日费用明细报表'
    )
  } else if (activeTab.value === 'qa') {
    exportToExcel(
      qaStats.top_questions.map((q, i) => ({ rank: i + 1, question: q.question, count: q.count })),
      [{ header: '排名', key: 'rank' }, { header: '问题', key: 'question' }, { header: '次数', key: 'count' }],
      '热门问题排行'
    )
  }
}

onMounted(async () => {
  await fetchPricing()
  await fetchData()
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-tags {
  display: flex;
  gap: 4px;
}

.filter-tag {
  cursor: pointer;
  padding: 2px 12px;
  border-radius: 4px;
  transition: all 0.2s;
  font-size: 13px;
  margin-right: 0 !important;
}

.filter-tag:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}
</style>
