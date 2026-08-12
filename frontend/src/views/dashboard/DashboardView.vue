<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">首页仪表盘</h1>
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
          :placeholder="['开始日期', '结束日期']"
          size="small"
          @change="onDateRangeChange"
          style="width: 240px"
        />
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-card-label">向量总 Token</div>
        <div class="stat-card-value">{{ formatNumber(costSummary.total_embedding_tokens) }}</div>
        <div class="stat-card-trend text-secondary">向量化切片累计</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">对话输入 Token</div>
        <div class="stat-card-value">{{ formatNumber(costSummary.total_chat_input_tokens) }}</div>
        <div class="stat-card-trend text-secondary">用户提问累计</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">对话输出 Token</div>
        <div class="stat-card-value">{{ formatNumber(costSummary.total_chat_output_tokens) }}</div>
        <div class="stat-card-trend text-secondary">AI回答累计</div>
      </div>
      <div class="stat-card" style="border-left: 3px solid var(--brand-600)">
        <div class="stat-card-label">预估总费用</div>
        <div class="stat-card-value" style="color: var(--brand-600)">
          {{ formatCost(costSummary.total_estimated_cost) }}
        </div>
        <div class="stat-card-trend text-secondary">实时计算</div>
      </div>
    </div>

    <!-- 趋势图 -->
    <div class="card" style="margin-bottom: var(--space-6)">
      <div class="card-header">费用趋势 (近{{ trendDays }}天)</div>
      <div class="card-body">
        <div ref="trendChartRef" style="height: 340px"></div>
      </div>
    </div>

    <!-- 底部双栏 -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6)">
      <!-- 用户维度 -->
      <div class="card">
        <div class="card-header">用户费用 TOP10</div>
        <div class="card-body" style="padding: 0">
          <a-table
            :columns="userColumns"
            :data-source="costSummary.by_user.slice(0, 10)"
            :pagination="false"
            size="small"
            row-key="user_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'cost'">
                {{ formatCost(record.cost) }}
              </template>
              <template v-if="column.key === 'tokens'">
                {{ formatNumber(record.tokens) }}
              </template>
            </template>
          </a-table>
        </div>
      </div>

      <!-- 知识库维度 -->
      <div class="card">
        <div class="card-header">知识库费用 TOP10</div>
        <div class="card-body" style="padding: 0">
          <a-table
            :columns="kbColumns"
            :data-source="costSummary.by_kb.slice(0, 10)"
            :pagination="false"
            size="small"
            row-key="kb_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'cost'">
                {{ formatCost(record.cost) }}
              </template>
              <template v-if="column.key === 'tokens'">
                {{ formatNumber(record.tokens) }}
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

const { formatCost, fetchPricing } = useCost()

const trendDays = ref(30)
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
      const weekStart = today.startOf('week').add(1, 'day')
      return {
        start_date: weekStart.format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'month':
      return {
        start_date: today.startOf('month').format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'quarter':
      const quarterStart = today.startOf('quarter')
      return {
        start_date: quarterStart.format('YYYY-MM-DD'),
        end_date: today.format('YYYY-MM-DD'),
      }
    case 'year':
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

const costSummary = reactive<CostSummaryResponse>({
  period_start: '',
  period_end: '',
  total_embedding_tokens: 0,
  total_chat_input_tokens: 0,
  total_chat_output_tokens: 0,
  total_estimated_cost: 0,
  by_user: [],
  by_kb: [],
  by_day: [],
})

const userColumns = [
  { title: '用户', dataIndex: 'username', key: 'username' },
  { title: 'Token', dataIndex: 'tokens', key: 'tokens', align: 'right' as const },
  { title: '费用', dataIndex: 'cost', key: 'cost', align: 'right' as const, width: 120 },
]

const kbColumns = [
  { title: '知识库', dataIndex: 'kb_name', key: 'kb_name' },
  { title: 'Token', dataIndex: 'tokens', key: 'tokens', align: 'right' as const },
  { title: '费用', dataIndex: 'cost', key: 'cost', align: 'right' as const, width: 120 },
]

async function fetchData() {
  const dateParams = getDateRangeByFilter(quickFilter.value)
  const params: Record<string, string> = { ...dateParams }

  // 获取费用汇总
  try {
    const res = await getCostSummaryApi(params)
    Object.assign(costSummary, res)
  } catch { /* empty */ }

  // 获取趋势数据
  try {
    const trend = await getUsageTrendApi(90, params.start_date, params.end_date)
    renderTrendChart(trend)
  } catch { /* empty */ }
}

function onDateRangeChange() {
  fetchData()
}

function renderTrendChart(data: UsageTrendResponse) {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['向量 Token', '对话输入', '对话输出', '预估费用'],
      bottom: 0,
    },
    grid: {
      left: 50,
      right: 60,
      top: 20,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLabel: {
        formatter: (v: string) => dayjs(v).format('MM-DD'),
      },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Token',
        axisLabel: { formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v },
      },
      {
        type: 'value',
        name: '费用 (¥)',
        axisLabel: { formatter: (v: number) => `¥${v.toFixed(2)}` },
      },
    ],
    series: [
      {
        name: '向量 Token',
        type: 'bar',
        data: data.embedding_tokens,
        itemStyle: { color: '#3b82f6' },
      },
      {
        name: '对话输入',
        type: 'bar',
        data: data.chat_input_tokens,
        itemStyle: { color: '#22c55e' },
      },
      {
        name: '对话输出',
        type: 'bar',
        data: data.chat_output_tokens,
        itemStyle: { color: '#f59e0b' },
      },
      {
        name: '预估费用',
        type: 'line',
        yAxisIndex: 1,
        data: data.costs,
        itemStyle: { color: '#ef4444' },
        lineStyle: { width: 2 },
        symbol: 'circle',
        symbolSize: 4,
      },
    ],
  })
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
