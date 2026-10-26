// 后端接口封装：开发环境经 Vite 代理转发到 FastAPI(127.0.0.1:8000)
async function apiGet(path) {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`请求失败 ${res.status}`)
  return res.json()
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let msg = `请求失败 ${res.status}`
    try {
      const j = await res.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* keep default */ }
    throw new Error(msg)
  }
  return res.json()
}

export const getStats = () => apiGet('/api/stats')
export const getGraph = (center = '', depth = 2) =>
  apiGet(`/api/graph?center=${encodeURIComponent(center)}&depth=${depth}`)
export const askOne = (mode, question) => apiPost(`/api/qa/${mode}`, { question })
export const getEvaluation = () => apiGet('/api/evaluation')
export const saveEvaluation = (rows) => apiPost('/api/evaluation', rows.map(row => ({
  ...row,
  // FastAPI 的 ScoreRow 将评分字段定义为字符串；数字控件会产生 number。
  accuracy: String(row.accuracy ?? ''),
  logic: String(row.logic ?? ''),
})))
