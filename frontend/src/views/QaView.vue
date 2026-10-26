<template>
  <div>
    <header class="page-heading"><div><h1>问答实验</h1><p>并排查看回答、检索证据并完成评分</p></div></header>
    <div class="toolbar">
      <el-input
        v-model="question"
        placeholder="输入设备运维问题，如：设备过载报警会触发哪些保护机制？"
        clearable
        @keyup.enter="ask"
      />
      <el-button type="primary" :loading="loading" @click="ask">三类系统对比问答</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" style="margin-bottom: 12px" />
    <div v-if="started" class="answer-list">
      <el-card v-for="card in cards" :key="card.key" shadow="never" class="qa-card">
          <template #header>
            <span class="badge">{{ card.title }}</span>
          </template>
          <div v-if="result[card.key]" class="answer-row"><div class="answer">{{ result[card.key].answer }}</div>

          <div class="score-box">
            <div class="score-heading"><b>评估此回答</b><span>对照回答与证据评分</span></div>
            <div class="score-grid">
              <label>准确率<el-input-number v-model="scoreFor(card).accuracy" :min="0" :max="10" size="small" controls-position="right" /></label>
              <label>逻辑完整<el-input-number v-model="scoreFor(card).logic" :min="0" :max="10" size="small" controls-position="right" /></label>
              <label>幻觉程度<el-select v-model="scoreFor(card).hallucination" size="small" placeholder="选择"><el-option label="无" value="无"/><el-option label="轻微" value="轻微"/><el-option label="严重" value="严重"/></el-select></label>
              <label>推理能力<el-select v-model="scoreFor(card).reasoning" size="small" placeholder="选择"><el-option label="强" value="强"/><el-option label="一般" value="一般"/><el-option label="弱" value="弱"/></el-select></label>
            </div>
            <el-input v-model="scoreFor(card).note" size="small" placeholder="评语（可选）" class="score-note" />
          </div></div>
          <el-skeleton v-else-if="status[card.key] === 'loading'" :rows="3" animated />
          <div v-else-if="status[card.key] === 'error'" class="inline-error">本路回答失败：{{ errors[card.key] }}</div>

          <el-collapse v-if="card.key !== 'pure_llm'" class="evidence">
            <el-collapse-item title="检索证据（点击展开）">
              <template v-if="card.key === 'graph_rag'">
                <template v-if="result[card.key]?.graph_links">
                  <div class="sub-title">图谱关联链路</div>
                  <pre class="mono">{{ result[card.key].graph_links }}</pre>
                </template>
                <template v-if="result[card.key]?.matched_entities?.length">
                  <div class="sub-title">命中实体</div>
                  <el-tag v-for="e in result[card.key].matched_entities" :key="e" size="small" class="tag">{{ e }}</el-tag>
                </template>
              </template>
              <div class="sub-title">向量检索文档片段</div>
              <pre class="mono" v-for="(c, i) in result[card.key]?.chunks || []" :key="i">{{ c }}</pre>
            </el-collapse-item>
          </el-collapse>
      </el-card>
    </div>
    <div v-if="started" class="score-actions"><span>可以边阅读已完成的回答边评分，最后保存本题。</span><el-button type="primary" :loading="saving" @click="saveScores">保存本题评分</el-button></div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { askOne, getEvaluation, saveEvaluation } from '../api'

const question = ref('')
const loading = ref(false)
const error = ref('')
const result = ref({})
const started = ref(false), status = ref({}), errors = ref({})
const saving = ref(false)
const scoreRows = ref([])

const cards = [
  { key: 'pure_llm', title: '纯大模型（无知识库）', model: '纯大模型' },
  { key: 'vector_rag', title: '传统文本 RAG（仅向量检索）', model: 'LangChain文本RAG' },
  { key: 'graph_rag', title: '图谱增强 RAG（Neo4j 双模态）', model: 'LangChain+Neo4j图谱RAG' },
]

function scoreFor(card) { return scoreRows.value.find(r => r.model === card.model) || {} }

async function ask() {
  if (!question.value.trim()) return
  loading.value = true; started.value = true; result.value = {}; errors.value = {}
  error.value = ''
  try {
    const q = question.value.trim()
    const stored = await getEvaluation().then(d => d.rows)
    const idx = stored.reduce((m, r) => Math.max(m, Number(r.idx) || 0), 0) + 1
    scoreRows.value = cards.map(card => stored.find(r => r.question === q && r.model === card.model) || {
      idx, question: q, model: card.model, accuracy: '', logic: '', hallucination: '', reasoning: '', note: '',
    })
    await Promise.all(cards.map(async card => { status.value[card.key]='loading'; try { result.value[card.key]=await askOne(card.key,q); status.value[card.key]='done' } catch(e) { errors.value[card.key]=e.message; status.value[card.key]='error' } }))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function saveScores() {
  saving.value = true
  try {
    const existing = await getEvaluation().then(d => d.rows)
    const next = [...existing]
    scoreRows.value.forEach(row => {
      const i = next.findIndex(r => r.question === row.question && r.model === row.model)
      if (i >= 0) next[i] = row
      else next.push(row)
    })
    await saveEvaluation(next)
    ElMessage.success('本题评分已保存，可在量化评估页查看图表')
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
</script>

<style scoped>
.answer-list{display:flex;flex-direction:column;gap:16px}.qa-card{min-height:220px}.badge{display:inline-block;padding:6px 10px;background:#f6f8fa;border-radius:4px;color:#1f2328;font-size:13px;font-weight:600}.answer-row{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:24px;align-items:start}.score-box{margin:0;padding:0 0 0 24px;border:0;border-left:1px solid #d1d9e0}.score-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;color:#1f2328;font-size:13px}.score-heading span{font-size:11px;color:#59636e}.score-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.score-grid label{display:flex;flex-direction:column;gap:6px;color:#59636e;font-size:11px}.score-grid :deep(.el-input-number),.score-grid :deep(.el-select){width:100%}.score-note{margin-top:12px}.score-actions{display:flex;justify-content:space-between;align-items:center;margin-top:16px;padding:16px;background:#fff;border:1px solid #d1d9e0;border-radius:8px;color:#59636e;font-size:12px}.inline-error{padding:12px;color:#1f2328;background:#f6f8fa;border-radius:6px}.answer{white-space:pre-wrap;line-height:1.8;font-size:14px;color:#1f2328}.evidence{margin-top:12px}.sub-title{font-size:12px;font-weight:600;color:#1f2328;margin:12px 0 6px}.mono{background:#f6f8fa;padding:10px;border-radius:4px;font-size:11px;line-height:1.7;white-space:pre-wrap;word-break:break-word;max-height:180px;overflow:auto;margin:0 0 8px}.tag{margin:0 6px 6px 0}@media(max-width:1000px){.answer-row{grid-template-columns:1fr}.score-box{border-left:0;border-top:1px solid #d1d9e0;padding:16px 0 0}}
</style>
