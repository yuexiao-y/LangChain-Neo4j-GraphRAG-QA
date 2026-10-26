# -*- coding: utf-8 -*-
#任务1：环境部署与初始化配置。

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")

# 本实验只访问本地 Neo4j 与国内大模型接口，Windows 系统代理（注册表配置）会导致Python 请求走代理而连接失败，这里统一绕过代理直连
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")

#  大模型配置（OpenAI 兼容接口）
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
EMBEDDING_NAME = os.getenv("EMBEDDING_NAME", "text-embedding-ada-002")
API_BASE = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL") or ""

# 对话模型与嵌入模型允许接入不同服务商（例如对话走学校接口、嵌入走智谱）。
# 未单独设置时回落到通用配置 OPENAI_API_KEY / OPENAI_API_BASE。
LLM_API_BASE = os.getenv("LLM_API_BASE") or API_BASE
LLM_API_KEY = os.getenv("LLM_API_KEY") or ""
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE") or API_BASE
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or ""

#  Neo4j 数据库配置 
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

#文本处理与检索参数（任务7 调优项）
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "300"))        # 文本切块大小
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "30"))   # 切块重叠字符数
TOP_K = int(os.getenv("TOP_K", "3"))                    # 向量检索 TopK
GRAPH_DEPTH = int(os.getenv("GRAPH_DEPTH", "2"))        # 图谱检索深度（跳数）

#  路径配置 
DOC_PATH = str(BASE_DIR / "device_doc.txt")
CHROMA_DIR = str(BASE_DIR / "chroma_db")
RESULTS_DIR = BASE_DIR / "results"
