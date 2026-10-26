# -*- coding: utf-8 -*-
"""
可视化后端：FastAPI 薄封装。
启动（项目根目录执行）：
  uvicorn backend.app:app --port 8000
"""
import re
import sys
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain_community.vectorstores import Chroma
from langchain_community.graphs import Neo4jGraph
from langchain_core.output_parsers import StrOutputParser

from config import (
    CHROMA_DIR, RESULTS_DIR, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, GRAPH_DEPTH,
)
import main

app = FastAPI(title="GraphRAG 设备运维知识图谱问答系统")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


llm = main.build_llm()
embeddings = main.build_embeddings()
vector_db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
retriever = vector_db.as_retriever(search_kwargs={"k": TOP_K})
rag_chain = main.build_vector_chain(llm, retriever)
graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USER, password=NEO4J_PASSWORD)
graph_chain = main.GRAPH_RAG_PROMPT | llm | StrOutputParser()


@app.get("/api/stats")
def stats():
    node_count = graph.query("MATCH (n) RETURN count(n) AS c")[0]["c"]
    rel_count = graph.query("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    entity_count = graph.query("MATCH (n:__Entity__) RETURN count(n) AS c")[0]["c"]
    return {
        "node_count": node_count, "rel_count": rel_count, "entity_count": entity_count,
        "model": main.MODEL_NAME, "embedding": main.EMBEDDING_NAME,
        "chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP,
        "top_k": TOP_K, "graph_depth": GRAPH_DEPTH,
    }


class QARequest(BaseModel):
    question: str

#生成单路回答，供对照接口和逐路展示接口复用。
def _answer_for_mode(mode: str, question: str):
    if mode == "pure_llm":
        return {"answer": main.pure_llm_qa(llm, question)}
    if mode == "vector_rag":
        result = rag_chain.invoke({"query": question})
        return {
            "answer": result["result"],
            "chunks": [d.page_content.strip() for d in result["source_documents"]],
        }
    if mode == "graph_rag":
        graph_text, matched = main.graph_retrieve(llm, graph, question)
        docs = retriever.invoke(question)
        context = main.merge_context(graph_text, docs)
        return {
            "answer": graph_chain.invoke({"context": context, "question": question}),
            "graph_links": graph_text,
            "matched_entities": matched,
            "chunks": [d.page_content.strip() for d in docs],
        }
    raise HTTPException(status_code=404, detail="未知问答模式")


@app.post("/api/qa")
def qa(req: QARequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    return {
        "question": question,
        "pure_llm": _answer_for_mode("pure_llm", question),
        "vector_rag": _answer_for_mode("vector_rag", question),
        "graph_rag": _answer_for_mode("graph_rag", question),
    }


@app.post("/api/qa/{mode}")

# 单路问答接口，供前端逐个呈现三类系统结果。
def qa_one(mode: str, req: QARequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    return _answer_for_mode(mode, question)


def _rows_to_graph(rows):
    nodes, links, seen = {}, [], set()

    def category(labels):
        for label in labels:
            if not label.startswith("__"):  
                return label
        return "实体"

    for r in rows:
        if "Document" in r["sl"] or "Document" in r["tl"] or r["name"] == "MENTIONS":
            continue
        for nid, labels in ((r["source"], r["sl"]), (r["target"], r["tl"])):
            if nid not in nodes:
                nodes[nid] = {"id": nid, "category": category(labels)}
        key = (r["source"], r["name"], r["target"])
        if key not in seen:
            seen.add(key)
            links.append({"source": r["source"], "target": r["target"], "name": r["name"]})
    return {"nodes": list(nodes.values()), "links": links}


@app.get("/api/graph")
#center 为空返回全图（实体间关系）；指定 center 时返回其 depth 跳内子图。
def get_graph(center: Optional[str] = None, depth: int = 0):
    if center:
        depth = depth or GRAPH_DEPTH
        cypher = f"""
        MATCH path = (n:__Entity__)-[rels*1..{int(depth)}]-(m:__Entity__)
        WHERE n.id CONTAINS $center
          AND all(node IN nodes(path) WHERE node:__Entity__ AND NOT node:Document)
          AND all(rel IN rels WHERE type(rel) <> 'MENTIONS')
        UNWIND rels AS r
        WITH DISTINCT startNode(r) AS a, type(r) AS name, endNode(r) AS b
        RETURN a.id AS source, labels(a) AS sl, name, b.id AS target, labels(b) AS tl
        LIMIT 300
        """
        rows = graph.query(cypher, {"center": center})
    else:
        rows = graph.query(
            "MATCH (a:__Entity__)-[r]->(b:__Entity__) "
            "WHERE NOT a:Document AND NOT b:Document AND type(r) <> 'MENTIONS' "
            "RETURN DISTINCT a.id AS source, labels(a) AS sl, type(r) AS name, "
            "b.id AS target, labels(b) AS tl LIMIT 600"
        )
    return _rows_to_graph(rows)


#量化评估
ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|$")
def _read_eval_rows():
    path = RESULTS_DIR / "evaluation_table.md"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        idx, question, model, acc, logic, hall, reason, note = m.groups()
        cells = [c.strip() for c in (question, model, acc, logic, hall, reason, note)]
        rows.append({
            "idx": int(idx),
            "question": cells[0], "model": cells[1],
            "accuracy": cells[2], "logic": cells[3],
            "hallucination": cells[4], "reasoning": cells[5], "note": cells[6],
        })
    return rows


@app.get("/api/evaluation")
def get_evaluation():
    return {"rows": _read_eval_rows()}


class ScoreRow(BaseModel):
    idx: int
    question: str
    model: str
    accuracy: str = ""
    logic: str = ""
    hallucination: str = ""
    reasoning: str = ""
    note: str = ""


@app.post("/api/evaluation")
#前端评分表保存：回写 evaluation_table.md（报告交付物，保持 Markdown 格式）。
def save_evaluation(rows: List[ScoreRow]):
    path = RESULTS_DIR / "evaluation_table.md"
    lines = main.EVAL_TABLE_HEADER + [
        f"| {r.idx} | {r.question} | {r.model} | {r.accuracy} | {r.logic} | "
        f"{r.hallucination} | {r.reasoning} | {r.note} |"
        for r in rows
    ]
    path.write_text(main.EVAL_TABLE_PREAMBLE + "\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "count": len(rows)}
