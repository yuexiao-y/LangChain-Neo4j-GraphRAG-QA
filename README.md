# LangChain-Neo4j GraphRAG QA

基于 LangChain + Neo4j 的设备运维知识图谱 RAG 专家问答系统。

实验指导书对应的完整实现：纯大模型问答 / 传统文本 RAG / LangChain+Neo4j 图谱增强 RAG 三类对照系统，覆盖任务 1-7 全链路。

## 目录结构

| 文件 | 说明 |
|---|---|
| `device_doc.txt` | 设备运维领域文档（当前为示例文档；如老师统一下发，直接替换内容并保持文件名不变） |
| `config.py` | 任务1：环境参数配置（读取 `.env` / 环境变量，含任务7调优参数） |
| `main.py` | 任务2-6 全链路：向量 RAG 构建、Neo4j 图谱构建、混合检索、三类问答对照测试 |
| `cypher_queries.py` | 任务3-4 图谱验证 + 指导书 8.1 必备 Cypher 查询 |
| `experiment_extension.py` | 指导书十一、拓展思考实现：约束抽取/多跳溯源/场景对照/降噪融合，报告输出到 `results/extension_task*.md` |
| `requirements.txt` | 依赖清单（比指导书安装命令多一个 `langchain-experimental`，见下文说明） |
| `backend/app.py` | FastAPI 接口：系统状态、三路问答、图谱查询、评分表读写 |
| `frontend/` | Vue 3 + Element Plus + ECharts 前端，含问答、知识图谱、量化评估页面 |
| `项目教程.md` | 按当前实现讲解概念、代码流程、接口和实验 |
| `分工.md` | 两人小组的建议分工模板；当前代码为集成后的完整项目 |
| `results/` | 运行后自动生成：三类问答完整结果 + 四维量化评分表 |
| `复现指南.md` | 从创建目录开始复现整个项目，说明手工创建与运行生成的文件 |

## 快速开始

1. 建议使用 Python 3.10/3.11，安装依赖（`requirements.txt` 未包含 FastAPI/Uvicorn 时需一并安装）：
   ```bash
   pip install -r requirements.txt fastapi uvicorn
   ```
2. 准备 Neo4j：安装 Neo4j Desktop，创建并启动本地数据库（默认 `bolt://localhost:7687`）。
3. 配置密钥：复制 `.env.example` 为 `.env`，填写模型 API 与 Neo4j 连接信息；聊天模型和嵌入模型可分别设置服务地址和密钥。
4. 运行实验：
   ```bash
   python main.py              # 重建向量库 + 图谱，再运行三类问答对照测试
   python main.py --skip-build # 复用已有索引，只重跑问答
   python cypher_queries.py    # 图谱验证查询（配合 Neo4j Browser 截图留存实验证据）
   python experiment_extension.py  # 指导书拓展思考实验（约束抽取/多跳溯源/场景对照/降噪融合）
   ```
5. 打开 `results/qa_results.md` 查看问答输出；人工评分可在前端量化评估页或 `results/evaluation_table.md` 完成。

> 注意：不带 `--skip-build` 会重建 Chroma 并清空 Neo4j 当前数据库后重建图谱。每次运行 `main.py`（含 `--skip-build`）都会覆盖 `results/qa_results.md` 和 `results/evaluation_table.md`，需要保留的人工评分请先备份。

## 可视化界面（Vue3 + Element Plus + ECharts）

前端只做展示，问答链路全部复用 `main.py`；后端为 FastAPI 薄封装（`backend/app.py`）。

首次使用先装前端依赖。在仓库根目录打开终端后执行：

```bash
cd frontend
npm ci
```

每次使用开两个终端：

```bash
# 终端 1：后端（复用已有 chroma_db 与 Neo4j 图谱，不重建）
uvicorn backend.app:app --port 8000

# 终端 2：前端开发服务器
cd frontend
npm run dev
```

浏览器打开 http://localhost:5173 ，三个页面：

| 页面 | 功能 |
|---|---|
| 问答实验 | 三种模式分别调用单路接口，某一路完成即显示；可查看检索证据，并在答案旁评分、保存本题评分 |
| 知识图谱 | ECharts 力导向图展示实体关系；可输入中心实体和深度探索子图、点击节点查看详情并继续探索 |
| 量化评估 | 查看评分表并编辑评分，保存回 `results/evaluation_table.md`，展示模型维度和题目准确率图表 |

## 实验任务 → 代码对应

| 实验任务 | 代码位置 |
|---|---|
| 任务1 环境部署与初始化配置 | `config.py`、`.env.example`、`requirements.txt` |
| 任务2 传统文本 RAG 系统搭建 | `main.py: build_vector_rag()` |
| 任务3 Neo4j 知识图谱构建（核心） | `main.py: build_neo4j_graph()` |
| 任务4 混合检索实现 | `main.py: extract_question_entities() / match_graph_nodes() / graph_retrieve() / merge_context()` |
| 任务5 三类问答系统对照开发 | `main.py: pure_llm_qa() / vector_rag_qa() / graph_rag_qa()` |
| 任务6 对照测试与量化评估 | `main.py: run_benchmark() + save_results()` |
| 任务7 系统优化 | `.env` 中 `CHUNK_SIZE / CHUNK_OVERLAP / TOP_K / GRAPH_DEPTH` |

## 与指导书参考代码的差异说明

1. **依赖补全**：指导书安装命令缺少 `langchain-experimental`，但参考代码从中 import 了 `LLMGraphTransformer`，`requirements.txt` 已补上。
2. **真正实现任务4的混合检索**：参考代码只用了 `GraphQAChain`（仅图谱检索，且其内置 Prompt 变量与自定义 Prompt 模板不匹配）。`main.py` 按任务4要求显式编排：实体识别 → 图谱 Cypher 多跳检索 + 向量检索双路召回 → 上下文去重整合 → 自定义 GraphRAG Prompt（图谱优先、文本补全）生成。
3. **Cypher 属性名差异**：`LLMGraphTransformer` 生成的实体名称存放在 `id` 属性且节点带 `__Entity__` 标签，因此 8.1 的 `e.name CONTAINS "设备"` 对应本实现的 `e.id CONTAINS "设备"`（`cypher_queries.py` 已按此编写）。
4. **关系计数修正**：参考代码 `MATCH ()-[r]-()` 会把每条关系数两遍，本实现使用有向 `MATCH ()-[r]->()` 单次计数。
5. **接口兼容**：代码用 `base_url` 显式传入接口地址，兼容各类 OpenAI 兼容中转接口；API Key 统一从环境变量/`.env` 读取，不在代码中硬编码。

## 常见问题

- **`LLMGraphTransformer` 报错或抽不出三元组**：检查模型 API 地址、密钥和模型名；本项目设置 `ignore_tool_usage=True`，但仍需模型能遵循结构化抽取提示。
- **Neo4j 连接失败**：确认 Neo4j Desktop 中数据库已 Start，`.env` 中 URI/账号/密码与 Neo4j Desktop 一致。
- **大模型接口报 ProxyError / APIConnectionError**：核对接口可达性、地址、密钥和模型名，并检查当前网络代理配置。`config.py` 默认设置 `NO_PROXY=*`，会让请求绕过代理；若服务必须通过代理访问，需要调整该设置。
- **重跑时报 Chroma 集合或维度冲突**：删除 `chroma_db/` 目录后重跑；修改 `CHUNK_SIZE` 等切块参数后必须重建向量库（不要用 `--skip-build`）。
- **图谱节点/关系数为 0**：检查模型接口是否正常返回结构化结果；实体抽取失败时 LangChain 会静默产出空图谱。
