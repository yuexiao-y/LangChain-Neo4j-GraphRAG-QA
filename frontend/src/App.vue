<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">G</div><div><strong>GraphRAG</strong><small>设备运维智能问答</small></div></div>
      <el-menu :default-active="active" class="menu" @select="k => (active = k)">
        <el-menu-item index="qa">问答实验</el-menu-item>
        <el-menu-item index="graph">知识图谱</el-menu-item>
        <el-menu-item index="eval">量化评估</el-menu-item>
      </el-menu>
      <div class="side-spacer"></div>
      <div v-if="stats" class="system-card"><div class="system-title">系统已连接</div><div class="metric"><span>图谱实体</span><b>{{ stats.entity_count ?? stats.node_count }}</b></div><div class="metric"><span>关系总数</span><b>{{ stats.rel_count }}</b></div><div class="model-label">语言模型</div><div class="model-name">{{ stats.model }}</div><div class="model-label">向量模型</div><div class="model-name">{{ stats.embedding }}</div></div>
      <el-alert v-else type="warning" :closable="false" class="backend-warn" title="等待后端连接" description="请启动 Neo4j 与 API 服务" />
    </aside>
    <main class="main"><header class="topbar"><div class="crumb">设备知识工程 <span>/</span> <b>{{ pageTitle }}</b></div><div class="top-status">实验环境</div></header><section class="page"><component :is="views[active]" /></section></main>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { getStats } from './api'
import QaView from './views/QaView.vue'
import GraphView from './views/GraphView.vue'
import EvalView from './views/EvalView.vue'
const views = { qa: QaView, graph: GraphView, eval: EvalView }
const titles = { qa: '问答实验', graph: '知识图谱', eval: '量化评估' }
const active = ref('qa'), stats = ref(null)
const pageTitle = computed(() => titles[active.value])
onMounted(async () => { try { stats.value = await getStats() } catch { /* 后端未就绪时显示连接提示 */ } })
</script>
<style>
:root{--ink:#1f2328;--muted:#59636e;--subtle:#818b98;--pale:#f6f8fa;--page:#fff;--line:#d1d9e0;--surface:#fff;--radius:6px;--hover:#eaeef2;--active:#eaeef2;--focus:#0969da}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif}
.shell{height:100vh;min-height:560px;display:flex}
.sidebar{width:240px;background:#fff;color:var(--ink);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:22px 14px 14px;flex:none}
.brand{display:flex;align-items:center;gap:12px;padding:0 8px 30px}
.brand-mark{height:34px;width:34px;border-radius:6px;background:#fff;border:1px solid var(--line);display:grid;place-items:center;color:var(--ink);font-size:19px;font-weight:700}
.brand strong{font-size:16px;letter-spacing:0;color:var(--ink)}.brand small{display:block;font-size:11px;color:var(--muted);margin-top:4px}
.nav-caption{font-size:11px;color:var(--muted);padding:0 10px 8px}
.menu{background:transparent;border:0}.menu .el-menu-item{height:40px;line-height:40px;margin:3px 0;border-radius:6px;color:#3d444d;font-size:13px}
.menu .el-menu-item:hover{background:var(--hover);color:var(--ink)}.menu .el-menu-item.is-active{background:var(--active);color:var(--ink);font-weight:600}
.side-spacer{flex:1}.system-card{padding:18px 8px 4px;background:transparent;border:0;border-top:1px solid var(--line);border-radius:0}
.system-title{font-size:12px;color:var(--ink);font-weight:600;margin-bottom:14px}.metric{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin:8px 0}.metric b{color:var(--ink);font-size:13px}
.model-label{font-size:10px;color:var(--muted);margin-top:13px}.model-name{color:var(--ink);font-size:11px;margin-top:4px;overflow:hidden;text-overflow:ellipsis}.sidebar-foot{font-size:10px;color:var(--muted);padding:14px 7px 0}
.backend-warn{margin:0 0 10px}.main{flex:1;min-width:0;overflow:auto}.topbar{height:58px;background:#f6f8fa;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 30px}
.crumb{font-size:13px;color:var(--muted)}.crumb span{padding:0 9px;color:var(--line)}.crumb b{color:var(--ink);font-weight:600}.top-status{font-size:11px;color:var(--muted)}
.page{padding:32px 36px 44px;max-width:1400px;margin:0 auto}.toolbar{display:flex;gap:12px;align-items:center;margin-bottom:22px;flex-wrap:wrap}.tip{font-size:12px;color:var(--muted)}
.chart,.chart-sm{width:100%;background:#fff;border-radius:var(--radius);border:1px solid var(--line);box-shadow:none}.chart{height:calc(100vh - 200px);min-height:440px}.chart-sm{height:340px}
.el-button{--el-border-radius-base:6px;border-radius:6px!important;box-shadow:none!important;transition:background-color .15s ease,color .15s ease,border-color .15s ease;font-size:13px!important;font-weight:500!important;min-height:36px}
.el-button:hover{background:var(--hover)!important;color:var(--ink)!important;border-color:var(--line)!important}.el-button:active{transform:none!important;background:#d8dee4!important}
.el-button--primary{--el-color-primary:#eaeef2;--el-color-primary-light-3:#eaeef2;--el-color-primary-light-5:#eaeef2;--el-color-primary-light-7:#f6f8fa;--el-color-primary-light-8:#f6f8fa;--el-color-primary-light-9:#f6f8fa;--el-color-primary-dark-2:#d8dee4;color:var(--ink)!important}
.el-button--primary:hover{background:#d8dee4!important;border-color:#d8dee4!important;color:var(--ink)!important}.el-button:not(.el-button--primary){background:transparent!important;border-color:transparent!important;color:var(--ink)!important}.el-button:not(.el-button--primary):hover{background:var(--hover)!important;border-color:transparent!important}
.el-input__wrapper,.el-select__wrapper{background:#fff!important;box-shadow:none!important;border-radius:6px!important;border:1px solid var(--line)!important;transition:border-color .15s ease,box-shadow .15s ease}
.el-input__wrapper.is-focus,.el-select__wrapper.is-focused{border-color:#80b4f1!important;box-shadow:0 0 0 2px #0969da20!important}.el-input-number,.el-input-number .el-input__wrapper{border-radius:6px!important}
.toolbar .el-input__wrapper,.controls .el-input__wrapper{height:40px;padding:0 12px!important;background:#fff!important}.el-button:focus-visible,.entity-choice:focus-visible,.relation:focus-visible{outline:2px solid #0969da55;outline-offset:2px}
.el-card{border-color:var(--line)!important;border-radius:6px!important;box-shadow:none!important}.el-card__header{padding:15px 18px!important;border-color:var(--line)!important}.el-card__body{padding:18px!important}
.el-table{--el-table-header-bg-color:#f6f8fa;--el-table-border-color:var(--line);--el-table-row-hover-bg-color:#f6f8fa;border-radius:6px;overflow:hidden}.el-table th.el-table__cell{font-weight:600;color:var(--ink)}.el-table td.el-table__cell{color:#3d444d}.el-table .cell{line-height:1.55}
.el-tag{--el-tag-bg-color:#f6f8fa!important;--el-tag-border-color:var(--line)!important;--el-tag-text-color:var(--ink)!important}.el-empty__description p{color:var(--muted)}
.el-alert{--el-alert-bg-color:#f6f8fa;--el-alert-border-color:var(--line);--el-alert-text-color:var(--ink);border:1px solid var(--line);border-radius:6px}.el-alert--error{--el-alert-bg-color:#fff8f8;--el-alert-text-color:#a40e26;--el-alert-border-color:#ffcecb}
.page-heading{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin:0 0 26px}.page-heading h1{font-size:25px;margin:4px 0;color:var(--ink);letter-spacing:-.35px}.page-heading p{font-size:13px;color:var(--muted);margin:0;line-height:1.6}
.menu .el-menu-item,.entity-choice,.relation{transition:background-color .15s ease,color .15s ease}
.qa-card .el-card__header{background:#fff}.score-actions{background:#f6f8fa}
@media(max-width:800px){.sidebar{width:190px;padding:20px 10px}.page{padding:24px 18px}.topbar{padding:0 18px}}
@media(max-width:580px){.sidebar{width:160px;padding:16px 8px}.brand{padding:0 4px 24px}.brand-mark{height:30px;width:30px;font-size:16px}.brand strong{font-size:14px}.brand small{font-size:9px}.menu .el-menu-item{font-size:12px;padding:0 10px!important}.nav-caption{padding-left:10px}.system-card{padding:10px 8px}.sidebar-foot{font-size:9px;padding-left:4px}.topbar{height:52px;padding:0 12px}.page{padding:18px 12px}.page-heading{margin-bottom:20px}.page-heading h1{font-size:21px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style>
