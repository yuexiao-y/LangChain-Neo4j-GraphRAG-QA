# -*- coding: utf-8 -*-
"""
运行方式：
  python main.py               # 首次运行：构建向量库与图谱，并执行三类问答对照测试
  python main.py --skip-build  # 复用已有 chroma_db 与 Neo4j 图谱，只重新问答
"""
import argparse
import json
import re
import shutil
from datetime import datetime

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.graphs import Neo4jGraph
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import (
    MODEL_NAME, EMBEDDING_NAME, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, GRAPH_DEPTH, DOC_PATH, CHROMA_DIR, RESULTS_DIR,
    LLM_API_BASE, LLM_API_KEY, EMBEDDING_API_BASE, EMBEDDING_API_KEY,
)

EVAL_TABLE_HEADER = [
    "| 序号 | 测试问题 | 测试模型 | 准确率(10分) | 逻辑完整性(10分) | 幻觉程度 | 推理能力 | 实验小结 |",
    "|---|---|---|---|---|---|---|---|",
]
EVAL_TABLE_PREAMBLE = (
    "# 实验对照测试记录表（四维量化评估，评分依据见指导书 8.2）\n\n"
    "打分说明：准确率、逻辑完整性各 10 分；幻觉程度分为无幻觉、轻微幻觉、严重幻觉"
    "（虚构关系/参数/流程）；推理能力考察多实体关联、故障溯源、链路推理。\n\n"
)


# 1. 模型初始化（任务1）
def build_llm():
    """初始化问答/实体抽取大模型（OpenAI 兼容接口）。
    API Key 读取环境变量 OPENAI_API_KEY；使用中转接口时通过 base_url 指定地址。
    """
    kwargs = {"model": MODEL_NAME, "temperature": 0.1}
    if LLM_API_BASE:
        kwargs["base_url"] = LLM_API_BASE
    if LLM_API_KEY:
        kwargs["api_key"] = LLM_API_KEY
    return ChatOpenAI(**kwargs)


# 初始化文本嵌入模型，用于 Chroma 向量化。
def build_embeddings():
    kwargs = {"model": EMBEDDING_NAME}
    if EMBEDDING_API_BASE:
        kwargs["base_url"] = EMBEDDING_API_BASE
    if EMBEDDING_API_KEY:
        kwargs["api_key"] = EMBEDDING_API_KEY
    return OpenAIEmbeddings(**kwargs)


#2. 传统文本 RAG（任务2）
#按当前配置加载并切分设备运维文档。
def load_split_docs():
    docs = TextLoader(DOC_PATH, encoding="utf-8").load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return splitter.split_documents(docs)

#创建返回检索文档的传统文本 RAG 问答链。
def build_vector_chain(llm, retriever):
    return RetrievalQA.from_chain_type(
        llm=llm, retriever=retriever, return_source_documents=True)

#传统文本向量 RAG 链路（LangChain 链路核心）
def build_vector_rag(llm, embeddings):
    split_docs = load_split_docs()
    vector_db = Chroma.from_documents(split_docs, embeddings, persist_directory=CHROMA_DIR)
    if hasattr(vector_db, "persist"):
        try:
            vector_db.persist()
        except Exception:
            pass

    retriever = vector_db.as_retriever(search_kwargs={"k": TOP_K})
    rag_chain = build_vector_chain(llm, retriever)
    print(f"传统文本 RAG 构建完成：{len(split_docs)} 个文本块"
          f"（chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}, top_k={TOP_K}）")
    return rag_chain, retriever, split_docs


# 3. Neo4j 知识图谱自动构建（任务3） 
def build_neo4j_graph(llm, split_docs):
    graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USER, password=NEO4J_PASSWORD)
    graph.query("MATCH (n) DETACH DELETE n") 
    print("LLMGraphTransformer 正在抽取三元组（每个文本块一次大模型调用，请耐心等待）...")

    transformer = LLMGraphTransformer(llm=llm, ignore_tool_usage=True)
    graph_docs = transformer.convert_to_graph_documents(split_docs)
    graph.add_graph_documents(graph_docs, baseEntityLabel=True, include_source=True)

    node_count = graph.query("MATCH (n) RETURN count(n) AS node_num")[0]["node_num"]
    rel_count = graph.query("MATCH ()-[r]->() RETURN count(r) AS rel_num")[0]["rel_num"]
    print(f"Neo4j 知识图谱构建完成：实体节点 {node_count} 个，关联关系 {rel_count} 条")
    return graph, node_count, rel_count


# 4. 图谱混合检索（任务4）
ENTITY_EXTRACT_PROMPT = (
    "从用户问题中抽取设备运维领域的关键实体（如设备、部件、故障、报警、操作、参数名称）。\n"
    "只输出 JSON 字符串数组，不要输出任何其他内容，示例：[\"过载报警\", \"检修流程\"]\n"
    "用户问题：{question}\n实体列表："
)

#任务4-1 前置：问题实体识别，供后续图谱实体匹配。
def extract_question_entities(llm, question):
    res = llm.invoke(ENTITY_EXTRACT_PROMPT.format(question=question))
    match = re.search(r"\[.*\]", res.content, re.S)
    if not match:
        return []
    try:
        names = json.loads(match.group())
        return [str(n).strip() for n in names if str(n).strip()][:6]
    except Exception:
        return []

#任务4-1：将问题实体匹配到图谱真实节点（CONTAINS 模糊匹配，容忍实体表述差异）。
def match_graph_nodes(graph, entity_names):
    matched = []
    for name in entity_names:
        rows = graph.query(
            "MATCH (e:__Entity__) WHERE e.id CONTAINS $name "
            "RETURN DISTINCT e.id AS id LIMIT 5",
            {"name": name},
        )
        matched.extend(r["id"] for r in rows)
    return sorted(set(matched))

#任务4-1：实体匹配 + Cypher 多跳子图检索，召回 GRAPH_DEPTH 跳内的关联链路。
def graph_retrieve(llm, graph, question, depth=GRAPH_DEPTH):
    
    entity_names = extract_question_entities(llm, question)
    if not entity_names:
        return "", []
    node_names = match_graph_nodes(graph, entity_names)
    if not node_names:
        return "", entity_names

    cypher = f"""
    MATCH (n:__Entity__)-[rels*1..{depth}]-(m:__Entity__)
    WHERE n.id IN $names
    UNWIND rels AS r
    WITH DISTINCT startNode(r) AS a, type(r) AS rel_type, endNode(r) AS b
    RETURN coalesce(a.id, '未知') AS a_name, rel_type, coalesce(b.id, '未知') AS b_name
    LIMIT 80
    """
    rows = graph.query(cypher, {"names": node_names})
    lines = [f"({r['a_name']})-[:{r['rel_type']}]->({r['b_name']})" for r in rows]
    return "\n".join(dict.fromkeys(lines)), node_names

#任务4-2：融合图谱结构化检索结果与向量语义检索结果，去重并整合为统一上下文。
def merge_context(graph_text, docs):
    parts = []
    if graph_text:
        parts.append("【图谱结构化关联链路】\n" + graph_text)
    seen, texts = set(), []
    for doc in docs:
        text = doc.page_content.strip()
        if text and text not in seen:
            seen.add(text)
            texts.append(text)
    if texts:
        parts.append("【相关文档片段】\n" + "\n---\n".join(texts))
    return "\n\n".join(parts)


#5. 三类问答链路（任务5）
# Prompt 优化：图谱优先、文本补全、无依据如实告知 —— 约束大模型抑制幻觉
GRAPH_RAG_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template=(
        "你是设备运维领域专家，请严格根据知识图谱关联关系与文档信息回答问题。\n"
        "优先使用图谱结构化关联逻辑梳理答案框架，结合文本细节补充内容，"
        "无依据则如实告知，禁止虚构、编造信息。\n\n"
        "图谱与文档上下文：\n{context}\n\n"
        "用户问题：{question}\n\n"
        "专业完整回答："
    ),
)


#纯大模型问答（无知识库）。
def pure_llm_qa(llm, question):
    return llm.invoke(question).content

#传统文本 RAG 问答（仅向量检索）。
def vector_rag_qa(rag_chain, question):
    return rag_chain.invoke({"query": question})["result"]


def graph_rag_qa(llm, retriever, graph, question):
    """图谱增强 RAG 问答（双模态混合检索）：

    ① 问题实体识别 + 图谱实体匹配 + Cypher 多跳检索，召回结构化关联链路；
    ② 向量语义检索召回相似文本细节；
    ③ 双路上下文去重合并，走自定义 GraphRAG Prompt（图谱优先、文本补全）生成答案。
    """
    graph_text, _ = graph_retrieve(llm, graph, question)
    docs = retriever.invoke(question)
    context = merge_context(graph_text, docs)
    chain = GRAPH_RAG_PROMPT | llm | StrOutputParser()
    return chain.invoke({"context": context, "question": question})


#6. 对照测试与量化评估（任务6）
# 题型覆盖（对应指导书任务6）：基础事实问答 / 流程规范问答 / 故障排查 / 多实体链路推理
TEST_QUESTIONS = [
    "CK6140 数控车床的额定电压、额定功率、主轴最高转速分别是多少？X、Z 轴分别控制工件哪个方向的尺寸？",
    "设备的三级保养分别是什么？请说明每级周期、执行人，并列举一级保养的一项工作内容。",
    "设备开机前必须完成哪五项检查？其中安全防护检查要确认哪些内容？",
    "主轴在低速 500 r/min 空载运行时异响明显，应该按什么顺序排查？最可能的原因是什么，对应如何处理？",
    "设备出现 ALM-03 过载报警时，报警触发条件是什么？请列出三类常见原因及对应处理措施，并说明复位后如何确认可以恢复加工。",
    "加工尺寸超差时，手册要求按什么顺序排查？如果问题涉及丝杠反向间隙，X 轴和 Z 轴的补偿值上限分别是多少？",
    "冷却泵不工作、喷淋压力不足、冷却液泡沫过多时，分别应检查或处理什么？这些处理分别涉及冷却系统的哪些部件或参数？",
    "设备运行时触发过载报警，同时发现导轨缺油、丝杠附近有切屑。请说明这两项异常如何导致过载，应该如何处理；重新启动前还要经过哪些确认步骤？",
]


#三类问答系统逐一回答测试问题集，打印并记录完整输出。
def run_benchmark(llm, rag_chain, retriever, graph):
    records = []
    for idx, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n===== 测试问题 {idx}：{question} =====")
        answers = {
            "纯大模型": pure_llm_qa(llm, question),
            "LangChain文本RAG": vector_rag_qa(rag_chain, question),
            "LangChain+Neo4j图谱RAG": graph_rag_qa(llm, retriever, graph, question),
        }
        for model_name, answer in answers.items():
            print(f"\n【{model_name}回答】\n{answer}")
        records.append({"idx": idx, "question": question, "answers": answers})
    return records


#输出三类问答完整结果与四维量化评分表（对应指导书第九节记录表）。
def save_results(records, node_count, rel_count):
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result_path = RESULTS_DIR / "qa_results.md"
    lines = [
        f"# 三类问答系统对照测试结果（{stamp}）",
        "",
        f"- 模型：{MODEL_NAME}｜嵌入模型：{EMBEDDING_NAME}",
        f"- 参数：chunk_size={CHUNK_SIZE}, chunk_overlap={CHUNK_OVERLAP}, "
        f"top_k={TOP_K}, graph_depth={GRAPH_DEPTH}",
        f"- 图谱规模：实体节点 {node_count} 个，关联关系 {rel_count} 条",
        "",
    ]
    for rec in records:
        lines.append(f"## 测试问题 {rec['idx']}：{rec['question']}")
        for model_name, answer in rec["answers"].items():
            lines.append(f"### 【{model_name}】\n\n{answer}\n")
    result_path.write_text("\n".join(lines), encoding="utf-8")

    # 四维量化评估表：准确率/逻辑完整性 10 分制，幻觉程度分无/轻微/严重，推理能力定性
    table_path = RESULTS_DIR / "evaluation_table.md"
    rows = EVAL_TABLE_HEADER.copy()
    for rec in records:
        for model_name in rec["answers"]:
            rows.append(f"| {rec['idx']} | {rec['question']} | {model_name} |  |  |  |  |  |")
    table_path.write_text(
        EVAL_TABLE_PREAMBLE + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    print(f"\n✅ 测试结果已保存：{result_path}")
    print(f"✅ 评分表已生成（评分列待人工填写）：{table_path}")


# 7. 主程序 
def main():
    parser = argparse.ArgumentParser(description="LangChain+Neo4j GraphRAG 三类问答对照实验")
    parser.add_argument("--skip-build", action="store_true",
                        help="复用已有 chroma_db 向量库与 Neo4j 图谱，跳过重建（调参对比时省 token）")
    args = parser.parse_args()

    llm = build_llm()
    embeddings = build_embeddings()

    if args.skip_build:
        print("跳过索引构建，复用已有向量库与图谱")
        vector_db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
        retriever = vector_db.as_retriever(search_kwargs={"k": TOP_K})
        rag_chain = build_vector_chain(llm, retriever)
        graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USER, password=NEO4J_PASSWORD)
        node_count = graph.query("MATCH (n) RETURN count(n) AS c")[0]["c"]
        rel_count = graph.query("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    else:
        # 重建前清空旧的本地向量库，避免切块参数变化后向量库残留旧数据
        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
        print("正在构建传统文本向量 RAG 知识库...")
        rag_chain, retriever, split_docs = build_vector_rag(llm, embeddings)
        graph, node_count, rel_count = build_neo4j_graph(llm, split_docs)

    records = run_benchmark(llm, rag_chain, retriever, graph)
    save_results(records, node_count, rel_count)


if __name__ == "__main__":
    main()
