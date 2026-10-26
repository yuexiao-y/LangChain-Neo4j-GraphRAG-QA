# -*- coding: utf-8 -*-
"""十一、实验拓展思考：四个拓展实验的可运行实现。

拓展1  自定义实体/关系约束优化三元组抽取：
       用 LLMGraphTransformer 的 allowed_nodes / allowed_relationships 限制抽取范围，
       与无约束模式在内存中对比节点数、关系类型数与领域命中率（不写 Neo4j，不污染主图谱）。
拓展2  多跳 Cypher 故障溯源：同一中心实体在 depth=1/2/3 下的关联链路数量与信息变化，
       分析"跳数太少漏信息、跳数太大引噪声"的权衡。
拓展3  简单问答 vs 复杂推理：设计两组题型（单事实 / 多实体链路），
       对照传统文本 RAG 与 GraphRAG 的回答差异，验证各自适配场景。
拓展4  检索降噪 + 权重融合：图谱链路按"实体命中连通子图"过滤噪声边；
       文本块按 α·向量相似分 + (1-α)·图谱实体命中分 融合重排。

前置条件：
  - 拓展1 仅需大模型接口；
  - 拓展2/3/4 需先运行过一次 python main.py（chroma_db 向量库与 Neo4j 图谱已存在）。

用法（项目根目录执行）：
  python experiment_extension.py            # 依次运行拓展 1~4
  python experiment_extension.py --only 2   # 只运行指定拓展（1/2/3/4）
  python experiment_extension.py --depth-max 3 --alpha 0.6
"""
import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from langchain_community.graphs import Neo4jGraph
from langchain_community.vectorstores import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_experimental.graph_transformers import LLMGraphTransformer

import main
from config import (
    CHROMA_DIR, RESULTS_DIR, TOP_K,
)


# 拓展 1：自定义实体/关系约束优化三元组抽取 
# 领域关键词白名单（按数控车床运维文档定制）：用于度量抽取出的实体有多少落在领域内
DOMAIN_KEYWORDS = [
    "设备", "车床", "电机", "主轴", "轴承", "卡盘", "尾座", "刀架", "丝杠", "导轨",
    "润滑", "冷却", "电气", "传感器", "PLC", "伺服", "故障", "报警", "过载", "异响",
    "振动", "保护", "检修", "维护", "保养", "检查", "参数", "电压", "电流", "转速",
    "油位", "乳化液", "冷却液", "导轨油", "皮带", "齿轮", "复位", "精度", "防锈",
    "防护", "试运行", "功率", "夹紧",
]

# 自定义实体类型约束：只允许抽取这 9 类实体，过滤"文档/章节/时间"等无价值节点
ALLOWED_NODES = [
    "设备", "部件", "故障", "报警", "保护机制", "运行参数", "维护项目", "操作", "角色",
]

# 自定义关系类型约束：限定为运维语义关系，避免"提到/相关"这类空洞关系
ALLOWED_REL_TYPES = [
    "组成", "导致", "触发", "联动", "处理方式", "排查步骤", "维护周期",
    "执行角色", "包含", "参数为", "检查项目",
]

# 统计一批 GraphDocument 的节点/关系质量指标。
def _graph_stats(graph_docs):
   
    nodes, rel_types = [], set()
    for gd in graph_docs:
        nodes.extend(n.id for n in gd.nodes)
        rel_types.update(r.type for r in gd.relationships)
    hit = sum(1 for n in nodes if any(k in n for k in DOMAIN_KEYWORDS))
    return {
        "node_total": len(nodes),
        "node_unique": len(set(nodes)),
        "rel_types": sorted(rel_types),
        "domain_hit": hit,
        "domain_ratio": f"{hit / len(nodes) * 100:.1f}%" if nodes else "0%",
        "sample_nodes": list(dict.fromkeys(nodes))[:12],
    }

#拓展1：无约束 vs 实体/关系白名单约束 的三元组抽取质量对比（内存中完成）。
def ext1_constrained_extraction(llm):
    split_docs = main.load_split_docs()
    print(f" 拓展1：对 {len(split_docs)} 个文本块做两轮三元组抽取（每轮每块一次大模型调用）...")

    print("  [1/2] 无约束抽取中 ...")
    free_docs = LLMGraphTransformer(llm=llm, ignore_tool_usage=True) \
        .convert_to_graph_documents(split_docs)
    free = _graph_stats(free_docs)

    print("  [2/2] 白名单约束抽取中 ...")
    constrained_docs = LLMGraphTransformer(
        llm=llm,
        ignore_tool_usage=True,
        allowed_nodes=ALLOWED_NODES,
        allowed_relationships=ALLOWED_REL_TYPES,
    ).convert_to_graph_documents(split_docs)
    cons = _graph_stats(constrained_docs)

    lines = [
        f"# 拓展1：自定义实体/关系约束优化三元组抽取（{datetime.now():%Y-%m-%d %H:%M:%S}）",
        "",
        "| 指标 | 无约束 | 白名单约束 |",
        "|---|---|---|",
        f"| 抽取节点总数 | {free['node_total']} | {cons['node_total']} |",
        f"| 去重后节点数 | {free['node_unique']} | {cons['node_unique']} |",
        f"| 关系类型数 | {len(free['rel_types'])} | {len(cons['rel_types'])} |",
        f"| 领域关键词命中率 | {free['domain_ratio']} | {cons['domain_ratio']} |",
        "",
        f"**无约束关系类型**：{', '.join(free['rel_types']) or '（无）'}",
        "",
        f"**约束后关系类型**：{', '.join(cons['rel_types']) or '（无）'}"
        f"（白名单：{', '.join(ALLOWED_REL_TYPES)}）",
        "",
        f"**无约束节点样例**：{'、'.join(free['sample_nodes'])}",
        "",
        f"**约束后节点样例**：{'、'.join(cons['sample_nodes'])}",
        "",
        "## 结论分析",
        "1. 约束抽取的节点数通常更少但领域命中率更高，'文档/章节'类噪声实体被过滤；",
        "2. 关系类型收敛到运维语义（导致/触发/维护周期等），图谱可解释性更强；",
        "3. 代价是可能漏掉白名单之外的有价值实体，约束清单需按领域文档迭代调整；",
        "4. 工业实践中约束清单可由领域专家标注样例数据后总结生成。",
    ]
    out = RESULTS_DIR / "extension_task1_constraints.md"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"拓展1 完成：无约束节点 {free['node_unique']} 个（命中率 {free['domain_ratio']}）"
          f"→ 约束后 {cons['node_unique']} 个（命中率 {cons['domain_ratio']}）")
    print(f"   对比报告已保存：{out}")
    return free, cons


# 拓展 2：多跳 Cypher 故障溯源，同一问题在 depth=1..depth_max 下的图谱召回规模对比，观察多跳溯源效果。
def ext2_multi_hop(llm, graph, question, depth_max):
    print(f" 拓展2：多跳故障溯源（中心问题：{question}）")
    entities = main.extract_question_entities(llm, question)
    nodes = main.match_graph_nodes(graph, entities)
    if not nodes:
        print("未在图谱中匹配到实体，请确认已运行 python main.py 构建图谱")
        return None
    print(f"   命中实体：{'、'.join(nodes)}")

    lines = [
        f"# 拓展2：多跳 Cypher 故障溯源实验（{datetime.now():%Y-%m-%d %H:%M:%S}）",
        "",
        f"- 中心问题：{question}",
        f"- 命中实体：{'、'.join(nodes)}",
        "",
        "| 检索深度 | 召回关系链路数 | 涉及实体数 | 关系类型数 |",
        "|---|---|---|---|",
    ]
    depth_texts = {}
    for depth in range(1, depth_max + 1):
        # 变长路径长度不能用 Cypher 参数传入，depth 为 int，无注入风险
        cypher = f"""
        MATCH (n:__Entity__)-[rels*1..{int(depth)}]-(m:__Entity__)
        WHERE n.id IN $names
        UNWIND rels AS r
        WITH DISTINCT startNode(r) AS a, type(r) AS rel_type, endNode(r) AS b
        RETURN coalesce(a.id, '未知') AS a_name, rel_type, coalesce(b.id, '未知') AS b_name
        LIMIT 200
        """
        rows = graph.query(cypher, {"names": nodes})
        uniq = list(dict.fromkeys(
            f"({r['a_name']})-[:{r['rel_type']}]->({r['b_name']})" for r in rows))
        depth_texts[depth] = "\n".join(uniq)
        involved = len({r["a_name"] for r in rows} | {r["b_name"] for r in rows})
        rel_types = len({r["rel_type"] for r in rows})
        lines.append(f"| {depth} 跳 | {len(uniq)} | {involved} | {rel_types} |")
        print(f"   depth={depth}: 链路 {len(uniq)} 条，涉及实体 {involved} 个，关系类型 {rel_types} 种")

    lines += ["", "## 各深度召回链路明细", ""]
    for depth, text in depth_texts.items():
        lines += [f"### depth={depth}", "```", text or "（无）", "```", ""]

    lines += [
        "## 结论分析",
        "1. depth=1 只能召回中心实体的直接邻居，链路短，适合单事实问答；",
        "2. depth=2 召回'故障→机制→流程'类完整因果链，是多跳溯源的性价比最高点；",
        "3. depth≥3 链路数量近似指数增长，噪声比例上升且超出大模型上下文利用能力，需配合截断（LIMIT）与降噪；",
        "4. 因此生产系统常用 depth=2 起步，按召回量动态调整。",
    ]
    out = RESULTS_DIR / "extension_task2_multihop.md"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 拓展2 完成，报告已保存：{out}")
    return depth_texts


#拓展 3：简单问答 vs 复杂推理场景对照
SIMPLE_QUESTIONS = [
    "CK6140 数控车床的额定功率是多少？",
    "冷却液乳化液的浓度应控制在什么范围？",
    "润滑泵的自动供油周期是怎么设定的？",
]

COMPLEX_QUESTIONS = [
    "设备过载报警触发时显示什么报警代码？常见原因与对应的处理方式有哪些？",
    "主轴异响在不同转速下分别可能是什么原因？对应的处理方法是什么？",
    "设备停机超过30天需要执行哪些保养？重新启用前还要做什么？",
]

#加载已有 Chroma 向量库与 Neo4j 图谱（要求先跑过 python main.py）。
def _ensure_indexes():
    if not Path(CHROMA_DIR).exists():
        sys.exit("❌ 未找到 chroma_db/，请先运行 python main.py 构建向量库与图谱")
    embeddings = main.build_embeddings()
    vector_db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    retriever = vector_db.as_retriever(search_kwargs={"k": TOP_K})
    graph = Neo4jGraph(url=main.NEO4J_URI, username=main.NEO4J_USER,
                       password=main.NEO4J_PASSWORD)
    return retriever, graph

#拓展3：两组题型 × 两种 RAG 的对照回答，验证各自适配场景。
def ext3_simple_vs_complex(llm, retriever, graph):
    print(" 拓展3：简单问答 vs 复杂推理场景对照")
    groups = [("简单单事实题", SIMPLE_QUESTIONS), ("复杂多实体推理题", COMPLEX_QUESTIONS)]
    lines = [
        f"# 拓展3：简单问答 vs 复杂推理场景对照（{datetime.now():%Y-%m-%d %H:%M:%S}）",
        "",
        "每组题分别用「传统文本 RAG（仅向量检索）」与「图谱增强 RAG（双模态检索）」回答。",
        "",
    ]
    rag_chain = main.build_vector_chain(llm, retriever)
    for gname, questions in groups:
        print(f"   题组：{gname}")
        lines += [f"## {gname}", ""]
        for idx, q in enumerate(questions, 1):
            print(f"     [{idx}/{len(questions)}] {q}")
            t0 = time.time()
            vec = main.vector_rag_qa(rag_chain, q)
            t_vec = time.time() - t0

            t0 = time.time()
            graph_text, matched = main.graph_retrieve(llm, graph, q)
            docs = retriever.invoke(q)
            context = main.merge_context(graph_text, docs)
            graph_answer = (main.GRAPH_RAG_PROMPT | llm | StrOutputParser()) \
                .invoke({"context": context, "question": q})
            t_graph = time.time() - t0

            lines += [
                f"### 题目 {idx}：{q}",
                f"- 命中实体：{'、'.join(matched) or '（无）'}",
                f"- 耗时：向量RAG {t_vec:.1f}s ｜ 图谱RAG {t_graph:.1f}s",
                "",
                f"**【传统文本 RAG】**",
                "", vec, "",
                f"**【图谱增强 RAG】**",
                "", graph_answer, "",
            ]
    lines += [
        "## 结论分析",
        "1. 简单单事实题：两类 RAG 均能正确回答，向量 RAG 甚至更快——图谱检索的实体识别环节是额外开销；",
        "2. 复杂多实体推理题：向量 RAG 因 Top-K 截断常丢失后半问所需片段，出现'答一半'或逻辑断裂；",
        "   GraphRAG 依靠图谱链路补全多实体关联，答案完整性明显占优；",
        "3. 结论：简单场景用向量 RAG 更划算，多实体关联/故障溯源/流程链路场景 GraphRAG 优势显著；",
        "4. 生产折中方案：先用规则/分类器判断问题复杂度，动态选择检索策略。",
    ]
    out = RESULTS_DIR / "extension_task3_scenarios.md"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"拓展3 完成，报告已保存：{out}")


#拓展 4：检索降噪 + 向量-图谱权重融合
EDGE_RE = re.compile(r"^\((.+)\)-\[:(\w+)\]->\((.+)\)$")

#检索降噪：保留与种子实体连通的边（连通子图），丢弃与命中实体无关的噪声链路。
def denoise_graph_links(graph_text, seeds):
    if not graph_text:
        return "", []
    keep, kept_lines = set(seeds), []
    edges = [(m.group(1), m.group(2), m.group(3))
             for m in (EDGE_RE.match(line.strip()) for line in graph_text.splitlines())
             if m]
    changed = True
    while changed:
        changed = False
        for a, rel, b in edges:
            if a in keep or b in keep:
                line = f"({a})-[:{rel}]->({b})"
                if line not in kept_lines:
                    kept_lines.append(line)
                if a not in keep or b not in keep:
                    keep.update((a, b))
                    changed = True
    return "\n".join(kept_lines), sorted(keep)


def rerank_docs(docs, matched_entities, alpha=0.6):
    """权重融合重排：final = α·向量相似名次分 + (1-α)·图谱实体命中分。
    向量分按名次线性衰减（第 1 名 1.0，最后一名趋近 0）；
    图谱分 = 该文本块提到的命中实体占比。返回按最终得分降序的新文档列表。
    """
    n = max(len(docs), 1)
    scored = []
    for rank, doc in enumerate(docs):
        vec_score = (n - rank) / n
        text = doc.page_content
        graph_score = (sum(1 for e in matched_entities if e in text)
                       / len(matched_entities)) if matched_entities else 0.0
        final = alpha * vec_score + (1 - alpha) * graph_score
        scored.append((final, vec_score, graph_score, doc))
    scored.sort(key=lambda x: -x[0])
    return scored

#拓展4：对同一问题演示降噪前后图谱链路对比 + 文本块融合重排。
def ext4_denoise_fusion(llm, retriever, graph, question, alpha):
    print(f"拓展4：检索降噪 + 权限融合重排（问题：{question}，alpha={alpha}）")
    graph_text, matched = main.graph_retrieve(llm, graph, question)
    docs = retriever.invoke(question)
    if not graph_text:
        print("图谱无召回，无法演示降噪；请确认图谱已构建且问题含可命中实体")
        return

    denoised, kept_nodes = denoise_graph_links(graph_text, matched)
    scored = rerank_docs(docs, matched, alpha)

    order_before = [d.page_content[:24].replace("\n", " ") + "..." for d in docs]
    order_after = [f"{final:.3f}(向量{vec:.2f}+图谱{g:.2f}) {d.page_content[:20].replace(chr(10), ' ')}..."
                   for final, vec, g, d in scored]

    lines = [
        f"# 拓展4：检索降噪 + 向量-图谱权重融合重排（{datetime.now():%Y-%m-%d %H:%M:%S}）",
        "",
        f"- 测试问题：{question}",
        f"- 命中实体：{'、'.join(matched) or '（无）'}",
        f"- 融合公式：final = {alpha}·向量名次分 + {1 - alpha:.1f}·图谱实体命中分",
        "",
        "## 一、图谱链路降噪（连通子图过滤）",
        "",
        f"降噪前 {len(graph_text.splitlines())} 条链路 → 降噪后 {len(denoised.splitlines())} 条"
        f"（过滤 {len(graph_text.splitlines()) - len(denoised.splitlines())} 条与命中实体不连通的噪声边）",
        "",
        "### 降噪后链路",
        "```", denoised or "（无）", "```",
        "",
        "## 二、文本块融合重排",
        "",
        "### 重排前（纯向量序）",
        "\n".join(f"{i + 1}. {t}" for i, t in enumerate(order_before)),
        "",
        "### 重排后（融合得分序）",
        "\n".join(f"{i + 1}. {t}" for i, t in enumerate(order_after)),
        "",
        "## 结论分析",
        "1. 连通子图降噪可剔除 LIMIT 截断与模糊实体匹配带进的孤立噪声边，且不损失多跳链路；",
        "2. 融合重排让'既向量相似又提到命中实体'的文本块排到前面，等价于隐式的向量-图谱证据交叉验证；",
        "3. α 越大越信任向量相似度，α 越小越信任图谱证据；可通过测试集网格搜索最优 α；",
        "4. 工业级进阶方案：图谱社区划分（Leiden 算法 + 社区摘要，参考微软 GraphRAG）、RRF 倒数排名融合、",
        "   按关系类型加权的边重要性评分、检索后 LLM 重排（rerank）等。",
    ]
    out = RESULTS_DIR / "extension_task4_denoise_fusion.md"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 拓展4 完成：降噪后链路 {len(denoised.splitlines())} 条，报告已保存：{out}")


#主程序
def main():
    parser = argparse.ArgumentParser(description="实验拓展思考：四个拓展实验")
    parser.add_argument("--only", type=int, choices=[1, 2, 3, 4],
                        help="只运行指定拓展，缺省运行全部")
    parser.add_argument("--depth-max", type=int, default=3, help="拓展2 的最大检索深度")
    parser.add_argument("--alpha", type=float, default=0.6,
                        help="拓展4 的向量得分权重（0~1）")
    parser.add_argument("--question", type=str,
                        default="设备过载报警触发时显示什么报警代码？常见原因与处理方式有哪些？",
                        help="拓展2/4 使用的测试问题")
    args = parser.parse_args()
    tasks = [args.only] if args.only else [1, 2, 3, 4]

    llm = main.build_llm()

    # 拓展1 不需要数据库；拓展2/3/4 需要向量库与图谱
    need_db = any(t in tasks for t in (2, 3, 4))
    if 1 in tasks:
        ext1_constrained_extraction(llm)
    if need_db:
        retriever, graph = _ensure_indexes()
        if 2 in tasks:
            ext2_multi_hop(llm, graph, args.question, args.depth_max)
        if 3 in tasks:
            ext3_simple_vs_complex(llm, retriever, graph)
        if 4 in tasks:
            ext4_denoise_fusion(llm, retriever, graph, args.question, args.alpha)

    print("拓展实验执行完毕，全部报告保存在 results/extension_task*.md")


if __name__ == "__main__":
    main()
