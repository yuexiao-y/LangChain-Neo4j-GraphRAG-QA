# -*- coding: utf-8 -*-
"""任务3-4 图谱有效性验证 + 指导书 8.1 必备 Cypher 查询练习。

说明：LLMGraphTransformer 抽取的实体节点统一带 __Entity__ 标签，实体名称存放在
id 属性，因此指导书 8.1 中的 ``e.name CONTAINS "设备"`` 在本实现里对应
``e.id CONTAINS "设备"``。

两种用法：
  1) 将 QUERIES 中的语句复制到 Neo4j Browser 执行并截图（实验证据）；
  2) 直接运行本脚本自动逐条执行并打印结果。

运行：python cypher_queries.py
"""
from langchain_community.graphs import Neo4jGraph

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

QUERIES = [
    ("8.1-1 查看所有实体节点",
     "MATCH (n) RETURN n LIMIT 50"),
    ("8.1-2 查看所有关联关系",
     "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50"),
    ("8.1-3 检索设备故障关联信息",
     'MATCH (e:__Entity__)-[r]-(f) WHERE e.id CONTAINS "设备" RETURN e, r, f'),
    ("任务3-4 实体关联查询：过载报警的全部关联",
     'MATCH (e:__Entity__)-[r]-(f) WHERE e.id CONTAINS "过载" RETURN e, r, f'),
    ("任务3-4 故障关系检索：故障、原因与处理方式",
     'MATCH (a)-[r]->(b) WHERE a.id CONTAINS "故障" OR b.id CONTAINS "故障" '
     "RETURN a, r, b LIMIT 30"),
    ("任务3-4 设备运维规则查询：维护/保养类关系",
     'MATCH (a)-[r]->(b) WHERE a.id CONTAINS "维护" OR a.id CONTAINS "保养" '
     'OR b.id CONTAINS "维护" OR b.id CONTAINS "保养" RETURN a, r, b LIMIT 30'),
    ("拓展思考-2 多跳故障溯源：过载报警两层关联链路",
     'MATCH p=(a:__Entity__)-[*1..2]-(b:__Entity__) WHERE a.id CONTAINS "过载" '
     "RETURN p LIMIT 25"),
    ("图谱统计：实体数量与关系数量",
     "MATCH (n) WITH count(n) AS node_num "
     "MATCH ()-[r]->() RETURN node_num, count(r) AS rel_num"),
]


def main():
    graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USER, password=NEO4J_PASSWORD)
    for title, cypher in QUERIES:
        print(f"\n===== {title} =====")
        print(f"Cypher: {cypher}")
        try:
            rows = graph.query(cypher)
            if not rows:
                print("（无返回结果）")
            for row in rows[:20]:
                print(row)
            if len(rows) > 20:
                print(f"... 共 {len(rows)} 行，仅显示前 20 行")
            print("（请在 Neo4j Browser 执行同款语句并截图留存实验证据）")
        except Exception as exc:
            print(f"执行失败：{exc}")


if __name__ == "__main__":
    main()
