<template>
  <div class="graph-page">
    <header class="page-heading heading">
      <div><h1>设备知识图谱</h1></div>
      <div class="totals"><strong>{{ data.nodes.length }}</strong> 个实体 <span>/</span> <strong>{{ data.links.length }}</strong> 条关系 <small>本次检索</small></div>
    </header>
    <form class="controls" @submit.prevent="load(center)">
      <el-input v-model="center" placeholder="搜索实体，如：主轴、过载报警" clearable aria-label="中心实体" />
      <label class="depth-control"><span>探索深度</span><el-input-number v-model="depth" :min="1" :max="3" :disabled="!center.trim()" controls-position="right" aria-label="探索深度" /><small v-if="!center.trim()">输入中心实体后生效</small></label>
      <el-button type="primary" native-type="submit" :loading="loading">探索关联</el-button>
      <el-button native-type="button" :disabled="loading" @click="reset">返回全图</el-button>
    </form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
    <div class="workspace">
      <section class="map-panel">
        <div class="map-toolbar"><div><b>{{ appliedCenter ? '局部关联' : '知识概览' }}</b><span class="scope">{{ appliedCenter ? `${appliedCenter} · 向外最多 ${appliedDepth} 层` : '全图关系概览 · 输入中心实体后可按深度探索' }}</span></div><el-button size="small" @click="render">视图归位</el-button></div>
        <div class="legend"><span v-for="group in GROUPS" :key="group.name"><i :style="{ background: group.color }"></i>{{ group.name }}</span></div>
        <div class="canvas-wrap" v-loading="loading" element-loading-text="正在加载关联数据…">
          <div ref="chartEl" class="graph-canvas"></div>
          <div v-if="!loading && !visible.nodes.length" class="empty-state"><h3>{{ error ? '暂时无法加载图谱' : '没有可显示的关联' }}</h3><p>{{ appliedCenter ? '试试更短的实体名称，或返回全图。' : '请确认当前数据库中已构建实体关系。' }}</p><el-button @click="reset">重新加载全图</el-button></div>
          <div class="canvas-hint">滚轮缩放 · 拖拽移动 · 点击节点查看详情</div>
        </div>
        <footer class="map-footer"><span>显示 <b>{{ visible.nodes.length }}</b> / {{ data.nodes.length }} 个实体 · {{ visible.links.length }} 条关系</span><el-switch v-model="showAll" active-text="显示全部实体" @change="refresh" /></footer>
      </section>
      <aside class="inspector">
        <template v-if="selected">
          <div class="panel-caption">实体详情 <button class="close" aria-label="关闭实体详情" @click="selectedId = ''">×</button></div>
          <span class="category-tag">{{ groupFor(selected).name }}</span>
          <h2>{{ selected.id }}</h2><div class="raw-type">原始类型 · {{ selected.category }}</div>
          <el-button type="primary" class="explore-button" :disabled="loading" @click="exploreSelected">以此实体探索关联</el-button>
          <div class="section-title">直接关联 <span>{{ related.length }}</span></div>
          <div class="relation-list"><button v-for="(relation, i) in related" :key="i" class="relation" @click="selectNode(relation.other)"><span class="relation-name">{{ relation.outgoing ? '→' : '←' }} {{ relation.name }}</span><strong>{{ relation.other }}</strong></button><p v-if="!related.length" class="muted">本次返回的数据中没有直接关联。</p></div>
        </template>
        <template v-else>
          <div class="panel-caption">开始探索</div><h2>选择一个实体</h2><p class="intro">查看完整名称、原始类型和相邻关系，或从下面的关键实体开始。</p>
          <div class="section-title">关键实体 <span>按关联数量排序</span></div>
          <button v-for="node in ranked.slice(0, 8)" :key="node.id" class="entity-choice" @click="selectNode(node.id)"><span>{{ node.id }}</span><b>{{ degrees.get(node.id) || 0 }}</b></button>
        </template>
      </aside>
    </div>
    <p class="footnote">节点越大，关联越多。概览默认展示关联最多的 60 个实体；颜色是展示分组，原始类型可在详情中查看。</p>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { getGraph } from '../api'

const GROUPS = [
  { name: '设备与部件', color: '#269d91' },
  { name: '故障与原因', color: '#d87670' },
  { name: '操作与维护', color: '#5d85c5' },
  { name: '参数与规格', color: '#b29150' },
  { name: '安全与规则', color: '#8e78b7' },
  { name: '其他知识', color: '#8295a3' },
]
function groupFor(node) {
  const type = String(node.category || '').replace(/[^a-zA-Z\u4e00-\u9fa5]/g, '').toLowerCase()
  if (/fault|reason|cause|issue|condition|resistance|故障|原因/.test(type)) return GROUPS[1]
  if (/safety|hazard|rule|requirement|安全|规则/.test(type)) return GROUPS[4]
  if (/operation|action|maintenance|inspection|procedure|step|solution|replacement|操作|维护|保养|检修/.test(type)) return GROUPS[2]
  if (/parameter|specification|value|quantity|voltage|power|speed|dimension|measurement|duration|period|frequency|current|参数|规格/.test(type)) return GROUPS[3]
  if (/device|equipment|component|system|part|motor|bearing|gear|axis|tool|drive|mechanism|设备|部件|系统/.test(type)) return GROUPS[0]
  return GROUPS[5]
}
const center = ref(''), appliedCenter = ref(''), depth = ref(2), appliedDepth = ref(2), loading = ref(false), error = ref('')
const data = ref({ nodes: [], links: [] }), showAll = ref(false), selectedId = ref(''), chartEl = ref(null)
let chart, observer, requestId = 0
const degrees = computed(() => {
  const counts = new Map()
  data.value.links.forEach(link => [link.source, link.target].forEach(id => counts.set(id, (counts.get(id) || 0) + 1)))
  return counts
})
const ranked = computed(() => [...data.value.nodes].sort((a, b) => (degrees.value.get(b.id) || 0) - (degrees.value.get(a.id) || 0) || a.id.localeCompare(b.id)))
const visible = computed(() => {
  const nodes = showAll.value ? ranked.value : ranked.value.slice(0, 60)
  const ids = new Set(nodes.map(node => node.id))
  return { nodes, links: data.value.links.filter(link => ids.has(link.source) && ids.has(link.target)) }
})
const selected = computed(() => data.value.nodes.find(node => node.id === selectedId.value))
const related = computed(() => data.value.links.filter(link => link.source === selectedId.value || link.target === selectedId.value).map(link => ({ ...link, outgoing: link.source === selectedId.value, other: link.source === selectedId.value ? link.target : link.source })))

async function load(value = '') {
  const current = ++requestId
  loading.value = true; error.value = ''
  try {
    const term = value.trim()
    const response = await getGraph(term, depth.value)
    if (current !== requestId) return
    data.value = response; appliedCenter.value = term; appliedDepth.value = depth.value; selectedId.value = ''
    render()
  } catch (e) {
    if (current === requestId) error.value = `图谱加载失败：${e.message}`
  } finally { if (current === requestId) loading.value = false }
}
function reset() { center.value = ''; showAll.value = false; load('') }
function refresh() { selectedId.value = ''; render() }
function exploreSelected() { center.value = selectedId.value; load(center.value) }
function selectNode(id) {
  if (!visible.value.nodes.some(node => node.id === id)) { showAll.value = true; render() }
  selectedId.value = id
  chart?.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  chart?.dispatchAction({ type: 'highlight', seriesIndex: 0, name: id })
}
watch(selectedId, value => { if (!value) chart?.dispatchAction({ type: 'downplay', seriesIndex: 0 }) })
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const shortName = value => value.length > 10 ? value.slice(0, 10) + '…' : value
function render() {
  if (!chart) return
  const { nodes, links } = visible.value
  const nodesById = new Map(nodes.map(node => [node.id, node]))
  const labels = new Set(nodes.slice(0, nodes.length <= 25 ? nodes.length : 14).map(node => node.id))
  chart.setOption({
    animationDurationUpdate: 300,
    tooltip: { confine: true, backgroundColor: '#fff', borderColor: '#d1d9e0', padding: 12, textStyle: { color: '#1f2328', fontSize: 12 }, extraCssText: 'max-width:320px;white-space:normal;word-break:break-word;border-radius:6px;', formatter: p => p.dataType === 'edge' ? `${escape(p.data.source)}<br/>→ ${escape(p.data.name)} →<br/>${escape(p.data.target)}` : `<b>${escape(p.name)}</b><br/>${escape(p.data.rawCategory)} · ${degrees.value.get(p.name) || 0} 条关联` },
    series: [{
      type: 'graph', layout: 'force', left: '10%', right: '10%', top: '12%', bottom: '12%', roam: true, draggable: true, zoom: .65, scaleLimit: { min: .25, max: 4 },
      force: { repulsion: showAll.value ? 100 : 220, edgeLength: [65, 130], gravity: .16, friction: .65 },
      data: nodes.map((node, index) => ({
        id: node.id, name: node.id, rawCategory: node.category,
        x: Math.cos(index * 2.399) * Math.sqrt(index + 1) * 22, y: Math.sin(index * 2.399) * Math.sqrt(index + 1) * 22,
        symbolSize: Math.min(38, 13 + Math.sqrt(degrees.value.get(node.id) || 0) * 5),
        itemStyle: { color: groupFor(node).color, borderColor: '#fff', borderWidth: 1.5 },
        label: { show: labels.has(node.id) },
      })),
      links: links.map(link => ({ ...link, lineStyle: { color: groupFor(nodesById.get(link.source) || {}).color, opacity: .55, width: 1.2 } })),
      edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 5,
      label: { position: 'bottom', distance: 6, color: '#1f2328', fontSize: 11, backgroundColor: '#ffffffeb', padding: [3, 5], borderRadius: 3, formatter: p => shortName(p.name) },
      labelLayout: { hideOverlap: true },
      lineStyle: { color: '#c6c6c6', width: 1, opacity: .65, curveness: .08 },
      edgeLabel: { show: false, formatter: p => shortName(p.data.name), fontSize: 10, backgroundColor: '#fff', padding: 3 },
      emphasis: { focus: 'adjacency', label: { show: true }, edgeLabel: { show: nodes.length < 40 }, lineStyle: { color: '#444444', width: 2, opacity: 1 } },
      blur: { itemStyle: { opacity: .18 }, lineStyle: { opacity: .08 }, label: { opacity: .15 } },
    }],
  }, { notMerge: true })
}
onMounted(() => {
  chart = echarts.init(chartEl.value)
  chart.on('click', params => { if (params.dataType === 'node') selectNode(params.name) })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartEl.value)
  load('')
})
onBeforeUnmount(() => { requestId++; observer?.disconnect(); chart?.dispose(); chart = null })
</script>

<style scoped>
.heading{align-items:flex-end}.totals{font-size:12px;color:var(--muted);white-space:nowrap}.totals strong{font-size:20px;color:var(--ink);margin:0 5px}.totals>span{margin:0 8px;color:var(--line)}.totals small{display:block;text-align:right;font-size:10px;margin-top:5px}.controls{display:flex;align-items:center;gap:12px;margin-bottom:16px}.controls>.el-input{max-width:360px}.controls label{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--muted);white-space:nowrap}.controls .el-input-number{width:95px}.controls .el-button{margin-left:0}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:16px;align-items:start}.map-panel,.inspector{background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden;box-shadow:none}.map-toolbar{display:flex;align-items:center;justify-content:space-between;padding:18px 20px 14px;gap:8px}.map-toolbar b{font-size:13px;color:var(--ink)}.scope{display:block;font-size:10px;color:var(--muted);margin:5px 0 0;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.legend{padding:0 20px 14px;display:flex;gap:8px 16px;flex-wrap:wrap;border-bottom:1px solid var(--line)}.legend span{font-size:10px;color:var(--muted);display:flex;align-items:center;gap:6px}.legend i{width:7px;height:7px;flex:none;border-radius:50%}.canvas-wrap{position:relative;background:var(--surface)}.graph-canvas{height:calc(100vh - 350px);min-height:440px;width:100%}.canvas-hint{position:absolute;bottom:13px;left:15px;font-size:10px;color:var(--muted);pointer-events:none;background:#fff;padding:5px 8px;border-radius:4px}.map-footer{padding:10px 15px;display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}.map-footer b{color:var(--ink)}.map-footer :deep(.el-switch__label){font-size:11px}.inspector{padding:20px;max-height:calc(100vh - 240px);min-height:420px;overflow:auto}.panel-caption{font-size:9px;letter-spacing:1.4px;color:var(--muted);display:flex;justify-content:space-between;align-items:center}.close{border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:20px}.inspector h2{font-size:17px;line-height:1.6;color:var(--ink);margin:10px 0;overflow-wrap:anywhere}.intro,.muted{font-size:12px;color:var(--muted);line-height:1.8}.section-title{display:flex;align-items:center;justify-content:space-between;margin:24px 0 9px;font-size:12px;color:var(--ink)}.section-title>span{font-size:9px;color:var(--muted)}.entity-choice{display:flex;align-items:center;gap:9px;background:none;border:0;border-bottom:1px solid var(--line);width:100%;padding:12px 0;text-align:left;cursor:pointer;color:var(--ink)}.entity-choice>span{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px}.entity-choice b{font-size:10px;color:var(--muted);font-weight:400}.entity-choice:hover,.relation:hover{color:var(--ink);background:#eaeef2}.category-tag{display:inline-block;background:var(--pale);color:var(--ink);border-radius:4px;padding:4px 7px;font-size:10px;margin-top:20px}.raw-type{font-size:10px;color:var(--muted);overflow-wrap:anywhere}.explore-button{width:100%;margin-top:18px;font-size:12px}.relation{display:block;width:100%;border:1px solid var(--line);background:#fff;border-radius:6px;padding:10px;margin-bottom:8px;text-align:left;cursor:pointer}.relation-name{display:block;font-size:10px;color:var(--muted);overflow-wrap:anywhere}.relation strong{display:block;font-size:12px;font-weight:500;line-height:1.7;color:var(--ink);margin-top:4px;overflow-wrap:anywhere}.footnote{font-size:10px;color:var(--muted);line-height:1.8;margin:11px 0}.notice{margin-bottom:12px}.empty-state{position:absolute;inset:0;display:flex;justify-content:center;align-items:center;flex-direction:column;background:#fffffff2;color:var(--muted);text-align:center;padding:20px}.empty-state h3{font-size:15px;font-weight:600;color:var(--ink);margin:10px}.empty-state p{font-size:12px;margin:0 0 18px}@media(max-width:1100px){.workspace{grid-template-columns:minmax(0,1fr) 220px}.inspector{padding:15px}.controls{flex-wrap:wrap}}@media(max-width:800px){.workspace{grid-template-columns:1fr}.inspector{max-height:400px;min-height:0}.heading{align-items:flex-start}.totals{display:none}.controls>.el-input{max-width:none}.graph-canvas{height:480px}.map-footer{flex-wrap:wrap}.controls label{font-size:11px}}
.panel-caption{font-size:12px;letter-spacing:0;color:var(--muted)}
.controls>.el-input{height:40px}
.controls :deep(.el-input-number){width:84px;height:40px}
.controls :deep(.el-input-number .el-input__wrapper){height:40px!important;padding-right:30px!important}
.controls :deep(.el-input-number__increase),.controls :deep(.el-input-number__decrease){right:0;width:28px;height:50%;line-height:18px;background:#f6f8fa;color:#666;border-left:1px solid var(--line);transition:background-color .15s ease,color .15s ease}
.controls :deep(.el-input-number__increase){top:0;border-bottom:1px solid var(--line)}
.controls :deep(.el-input-number__decrease){bottom:0}
.controls :deep(.el-input-number__increase:hover),.controls :deep(.el-input-number__decrease:hover){background:#eaeef2;color:#1f2328}
</style>

