<template>
  <div v-loading="loading" class="eval-page">
    <header class="page-heading"><div><h1>量化评估</h1><p>根据三类问答结果填写评分并查看对比</p></div></header>
    <div class="toolbar" v-if="rows.length">
      <el-button type="primary" :loading="saving" @click="save">保存评分到 evaluation_table.md</el-button>
      <span class="tip">
        打分依据指导书 8.2：准确率/逻辑完整性 10 分制；幻觉程度填「无 / 轻微 / 严重」；推理能力填「强 / 一般 / 弱」
      </span>
    </div>

    <el-row v-if="rows.length" :gutter="16">
      <el-col :span="12"><div ref="radarEl" class="chart-sm"></div></el-col>
      <el-col :span="12"><div ref="barEl" class="chart-sm"></div></el-col>
    </el-row>
    <el-alert v-else title="暂无评分数据" type="info" :closable="false"
      description="请先运行 python main.py 生成 evaluation_table.md，再刷新本页" />

    <el-table v-if="rows.length" :data="rows" size="small" border style="margin-top: 16px">
      <el-table-column prop="idx" label="#" width="48" align="center" />
      <el-table-column prop="question" label="测试问题" min-width="170" show-overflow-tooltip />
      <el-table-column prop="model" label="测试模型" width="168" />
      <el-table-column label="准确率" width="86" align="center">
        <template #default="{ row }"><el-input v-model="row.accuracy" size="small" placeholder="0-10" /></template>
      </el-table-column>
      <el-table-column label="逻辑完整性" width="96" align="center">
        <template #default="{ row }"><el-input v-model="row.logic" size="small" placeholder="0-10" /></template>
      </el-table-column>
      <el-table-column label="幻觉程度" width="86" align="center">
        <template #default="{ row }"><el-input v-model="row.hallucination" size="small" placeholder="无/轻微/严重" /></template>
      </el-table-column>
      <el-table-column label="推理能力" width="86" align="center">
        <template #default="{ row }"><el-input v-model="row.reasoning" size="small" placeholder="强/一般/弱" /></template>
      </el-table-column>
      <el-table-column label="实验小结" min-width="150">
        <template #default="{ row }"><el-input v-model="row.note" size="small" /></template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { getEvaluation, saveEvaluation } from '../api'

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const radarEl = ref(null)
const barEl = ref(null)
let radar = null
let bar = null

const MODELS = ['纯大模型', 'LangChain文本RAG', 'LangChain+Neo4j图谱RAG']
const COLORS = ['#24292f', '#6e7781', '#afb8c1']

// 四维评分换算：数值列直接 parseFloat，幻觉程度/推理能力按关键词映射到 10 分制
function toScore(v, kind) {
  const s = (v || '').toString().trim()
  if (!s) return null
  if (kind === 'hall') {
    if (/严重/.test(s)) return 0
    if (/轻微|一般/.test(s)) return 5
    if (/无/.test(s)) return 10
    return null
  }
  if (kind === 'reason') {
    if (/强|是/.test(s)) return 10
    if (/一般/.test(s)) return 5
    if (/弱|否/.test(s)) return 0
    return null
  }
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

function avg(list) {
  const vals = list.filter(v => v !== null)
  return vals.length ? +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : 0
}

function modelScores(model) {
  const rs = rows.value.filter(r => r.model === model)
  return [
    avg(rs.map(r => toScore(r.accuracy, 'num'))),
    avg(rs.map(r => toScore(r.logic, 'num'))),
    avg(rs.map(r => toScore(r.hallucination, 'hall'))),
    avg(rs.map(r => toScore(r.reasoning, 'reason'))),
  ]
}

function renderCharts() {
  if (!rows.value.length) return
  const series = MODELS.filter(m => rows.value.some(r => r.model === m))
  const colors = MODELS.map((m, i) => (series.includes(m) ? COLORS[i] : null)).filter(Boolean)

  radar.setOption({
    title: { text: '四维能力雷达图（各模型平均分）', left: 'center', textStyle: { fontSize: 13, color: '#1f2328' } },
    legend: { bottom: 0, data: series },
    radar: {
      axisName: { color: '#59636e' }, splitLine: { lineStyle: { color: '#d1d9e0' } }, splitArea: { areaStyle: { color: ['#fff', '#f6f8fa'] } }, axisLine: { lineStyle: { color: '#d1d9e0' } },
      indicator: [
        { name: '问答准确率', max: 10 },
        { name: '逻辑完整性', max: 10 },
        { name: '幻觉抑制', max: 10 },
        { name: '推理能力', max: 10 },
      ],
      radius: '62%',
    },
    series: [{
      type: 'radar',
      data: series.map((m, i) => ({ name: m, value: modelScores(m), areaStyle: { opacity: 0.15 }, lineStyle: { color: colors[i] }, itemStyle: { color: colors[i] } })),
    }],
  }, true)

  const questions = [...new Set(rows.value.map(r => r.idx))].sort((a, b) => a - b)
  bar.setOption({
    title: { text: '各问题准确率对比（10分制）', left: 'center', textStyle: { fontSize: 13, color: '#1f2328' } },
    legend: { bottom: 0, data: series },
    grid: { top: 40, left: 40, right: 16, bottom: 60 },
    xAxis: { type: 'category', data: questions.map(q => `问题${q}`), axisLine: { lineStyle: { color: '#d1d9e0' } }, axisLabel: { color: '#59636e' } },
    yAxis: { type: 'value', max: 10, axisLabel: { color: '#59636e' }, splitLine: { lineStyle: { color: '#f6f8fa' } } },
    series: series.map((m, i) => ({
      name: m,
      type: 'bar',
      barGap: 0,
      data: questions.map(q => {
        const r = rows.value.find(x => x.idx === q && x.model === m)
        return toScore(r && r.accuracy, 'num') ?? 0
      }),
      itemStyle: { color: colors[i] },
    })),
  }, true)
}

async function load() {
  loading.value = true
  try {
    rows.value = await getEvaluation().then(d => d.rows)
    await nextTick()
    // 图表容器带 v-if，必须等数据到位、DOM 渲染后再初始化 echarts
    if (!radar && radarEl.value) radar = echarts.init(radarEl.value)
    if (!bar && barEl.value) bar = echarts.init(barEl.value)
    renderCharts()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await saveEvaluation(rows.value)
    ElMessage.success('已保存到 results/evaluation_table.md')
    renderCharts()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function onResize() {
  radar && radar.resize()
  bar && bar.resize()
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  radar && radar.dispose()
  bar && bar.dispose()
})
</script>
