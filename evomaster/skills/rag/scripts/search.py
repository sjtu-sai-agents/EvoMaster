#!/usr/bin/env python3
"""RAG Searcher - 向量检索工具

提供基于 FAISS 和 transformer embeddings 的语义检索功能。
支持本地 transformer 模型和 OpenAI embedding API。

设计目标：通用的"向量检索 +（可选）取回原始内容"组件。
- 向量检索：依赖 vec_dir 下的 `faiss.index` 与 `nodes.jsonl`
- 内容取回：可选加载 `nodes_data.json`，并通过 `content_path`（点路径）提取字段
"""

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any
from abc import ABC, abstractmethod

import numpy as np
import faiss

logger = logging.getLogger(__name__)


# ============================================
# Embedding 抽象基类和实现
# ============================================

class BaseEmbedder(ABC):
    """Embedding 模型的抽象基类"""
    
    @abstractmethod
    def encode(self, text: str) -> np.ndarray:
        """将文本编码为向量"""
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """返回 embedding 维度"""
        pass


class LocalTransformerEmbedder(BaseEmbedder):
    """本地 Transformer 模型 Embedder（HuggingFace）"""
    
    def __init__(self, model_name: str, device: str = "cpu"):
        import torch
        from transformers import AutoTokenizer, AutoModel
        
        self.model_name = model_name
        self.device = device
        
        # 静默加载模型
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            with contextlib.redirect_stderr(devnull):
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        
        # 获取 embedding 维度
        self._dimension = self.model.config.hidden_size
        logger.info(f"Initialized local transformer embedder: {model_name} on {device}, dim={self._dimension}")
    
    def encode(self, text: str) -> np.ndarray:
        import torch
        
        inputs = self.tokenizer(
            text,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            h = outputs.last_hidden_state
            attn = inputs["attention_mask"].unsqueeze(-1)
            # Mean pooling with attention weights
            emb = (h * attn).sum(dim=1) / attn.sum(dim=1)
        
        return emb.cpu().numpy()
    
    def get_dimension(self) -> int:
        return self._dimension


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI Embedding API Embedder"""
    
    def __init__(
        self,
        model: str = "text-embedding-3-large",
        api_key: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("OpenAI package not installed. Install with: pip install openai")
        
        self.model = model
        self.dimensions = dimensions
        
        # 优先使用传入参数，否则从环境变量读取
        self.api_key = api_key or os.environ.get("OPENAI_EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_EMBEDDING_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set via parameter, OPENAI_EMBEDDING_API_KEY or OPENAI_API_KEY env var.")
        
        # 初始化客户端
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        self.client = OpenAI(**client_kwargs)
        
        # 默认维度（text-embedding-3-large 默认 3072，可自定义）
        self._dimension = dimensions or 3072
        logger.info(f"Initialized OpenAI embedder: {model}, base_url={base_url}, dim={self._dimension}")
    
    def encode(self, text: str) -> np.ndarray:
        """调用 OpenAI embedding API"""
        kwargs = {
            "model": self.model,
            "input": text,
        }
        # text-embedding-3-* 系列支持 dimensions 参数
        if self.dimensions and "text-embedding-3" in self.model:
            kwargs["dimensions"] = self.dimensions
        
        response = self.client.embeddings.create(**kwargs)
        embedding = response.data[0].embedding
        return np.array([embedding], dtype=np.float32)
    
    def get_dimension(self) -> int:
        return self._dimension


def create_embedder(
    model: str | None = None,
    embedding_type: str = "auto",
    api_key: str | None = None,
    base_url: str | None = None,
    dimensions: int | None = None,
    device: str = "cpu",
) -> BaseEmbedder:
    """创建 Embedder 实例
    
    Args:
        model: 模型名称或路径
        embedding_type: "local", "openai", 或 "auto"（自动检测）
        api_key: OpenAI API key（仅 openai 类型需要）
        base_url: OpenAI API base URL（仅 openai 类型需要）
        dimensions: Embedding 维度（仅 openai 的 text-embedding-3-* 支持）
        device: 计算设备（仅 local 类型需要）
    
    Returns:
        BaseEmbedder 实例
    """
    # 自动检测类型
    if embedding_type == "auto":
        if model and ("text-embedding" in model or model.startswith("openai/")):
            embedding_type = "openai"
        elif api_key or os.environ.get("OPENAI_EMBEDDING_API_KEY"):
            embedding_type = "openai"
        else:
            embedding_type = "local"
    
    if embedding_type == "openai":
        return OpenAIEmbedder(
            model=model or "text-embedding-3-large",
            api_key=api_key,
            base_url=base_url,
            dimensions=dimensions,
        )
    else:
        # 本地模型
        default_model = "evomaster/skills/rag/local_models/all-mpnet-base-v2"
        return LocalTransformerEmbedder(
            model_name=model or default_model,
            device=device,
        )


def _find_project_root() -> Path:
    """查找项目根目录（包含 evomaster 目录的目录）。"""
    script_path = Path(__file__).resolve()
    current = script_path.parent
    while current != current.parent:
        if (current / "evomaster").exists() and (current / "evomaster").is_dir():
            return current
        current = current.parent
    cwd = Path.cwd()
    current = cwd
    while current != current.parent:
        if (current / "evomaster").exists() and (current / "evomaster").is_dir():
            return current
        current = current.parent
    if "EvoMaster_ROOT" in os.environ:
        root = Path(os.environ["EvoMaster_ROOT"])
        if root.exists() and (root / "evomaster").exists():
            return root
    raise RuntimeError(
        "无法找到项目根目录。请确保在 EvoMaster 项目目录结构中运行，或设置 EvoMaster_ROOT。"
    )


def _resolve_path(path_str: str, project_root: Path | None = None) -> Path:
    """将路径解析为绝对路径；evomaster/ 开头则相对项目根。"""
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    path_str_normalized = str(path).replace("\\", "/")
    if path_str_normalized.startswith("evomaster/"):
        if project_root is None:
            project_root = _find_project_root()
        return (project_root / path).resolve()
    return path.resolve()


class RAGSearcher:
    """
    通用 RAG Searcher，提供向量检索功能
    支持本地 transformer 模型和 OpenAI embedding API
    """

    def __init__(
        self,
        vec_dir: str,
        model_name: str = "evomaster/skills/rag/local_models/all-mpnet-base-v2",
        nodes_data_json: str | None = None,
        device: str = "cpu",
        node_id_key: str = "node_id",
        # OpenAI embedding 参数
        embedding_type: str = "auto",
        embedding_api_key: str | None = None,
        embedding_base_url: str | None = None,
        embedding_dimensions: int | None = None,
    ):
        """初始化 RAG Searcher

        Args:
            vec_dir: 向量数据库目录路径（包含 faiss.index, embeddings.npy, nodes.jsonl）
            model_name: 用于编码的模型名称（本地路径或 OpenAI 模型名）
            nodes_data_json: 节点数据 JSON 文件路径（可选，用于获取知识内容）
            device: 计算设备 ('cpu' 或 'cuda')，仅本地模型使用
            node_id_key: nodes.jsonl 每行 JSON 中作为 ID 的字段名（默认 'node_id'）
            embedding_type: "local", "openai", 或 "auto"（自动检测）
            embedding_api_key: OpenAI API key（仅 openai 类型需要）
            embedding_base_url: OpenAI API base URL（仅 openai 类型需要）
            embedding_dimensions: Embedding 维度（仅 openai 的 text-embedding-3-* 支持）
        """
        self.vec_dir = Path(vec_dir)
        self.model_name = model_name
        self.device = device
        self.node_id_key = node_id_key

        # 加载 FAISS index
        index_path = self.vec_dir / "faiss.index"
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {index_path}")
        self.index = faiss.read_index(str(index_path))
        logger.info(f"Loaded FAISS index from {index_path}")

        # 加载 embeddings（可选，用于调试）
        emb_path = self.vec_dir / "embeddings.npy"
        if emb_path.exists():
            self.emb = np.load(emb_path)
            logger.info(f"Loaded embeddings from {emb_path}")
        else:
            self.emb = None
            logger.warning(f"Embeddings file not found: {emb_path}")

        # 加载 node_id 映射
        nodes_jsonl_path = self.vec_dir / "nodes.jsonl"
        self.node_ids = []
        if nodes_jsonl_path.exists():
            with open(nodes_jsonl_path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    if line.strip():
                        obj = json.loads(line)
                        # 优先使用指定的 node_id_key，如果没有则尝试使用 task_name，最后使用索引
                        if self.node_id_key in obj:
                            node_id = obj[self.node_id_key]
                        elif "task_name" in obj:
                            node_id = obj["task_name"]
                            logger.debug(f"Using 'task_name' as node_id for line {idx}: {node_id}")
                        else:
                            # 使用索引作为 node_id
                            node_id = str(idx)
                            logger.debug(f"Using index as node_id for line {idx}: {node_id}")
                        self.node_ids.append(node_id)
            logger.info(f"Loaded {len(self.node_ids)} node IDs from {nodes_jsonl_path}")
        else:
            logger.warning(f"Nodes JSONL file not found: {nodes_jsonl_path}")

        # 加载 nodes_data（如果提供）
        self.nodes_data = {}
        if nodes_data_json:
            nodes_data_path = Path(nodes_data_json)
            if nodes_data_path.exists():
                with open(nodes_data_path, "r", encoding="utf-8") as f:
                    self.nodes_data = json.load(f)
                logger.info(f"Loaded nodes data from {nodes_data_path}")
            else:
                logger.warning(f"Nodes data file not found: {nodes_data_path}")

        # 初始化 embedding 模型（支持本地模型和 OpenAI API）
        self.embedder = create_embedder(
            model=model_name,
            embedding_type=embedding_type,
            api_key=embedding_api_key,
            base_url=embedding_base_url,
            dimensions=embedding_dimensions,
            device=device,
        )

    @staticmethod
    def _get_by_dotted_path(obj: Any, dotted_path: str, default: Any = None) -> Any:
        """使用点路径从 dict/对象中取值，例如 'content.text'。"""
        if dotted_path is None or dotted_path == "":
            return obj
        cur: Any = obj
        for key in dotted_path.split("."):
            if cur is None:
                return default
            if isinstance(cur, dict):
                cur = cur.get(key, default)
            else:
                cur = getattr(cur, key, default)
        return cur

    def _default_content_candidates(self) -> list[str]:
        # 常见字段兜底（尽量通用，避免绑定某个项目）
        return [
            "content.text",
            "content.page_content",
            "content.knowledge",
            "content.data",
            "content",
            "text",
            "page_content",
            "knowledge",
            "data",
        ]

    def encode(self, text: str) -> np.ndarray:
        """将文本编码为向量

        Args:
            text: 输入文本

        Returns:
            编码后的向量（numpy array）
        """
        return self.embedder.encode(text)

    def search_similar(
        self,
        query_emb: np.ndarray,
        top_k: int = 5,
        distance_threshold: float | None = None
    ) -> list[tuple[str, float]]:
        """搜索相似节点

        Args:
            query_emb: 查询向量
            top_k: 返回前 k 个结果
            distance_threshold: 距离阈值，超过此阈值的结果将被过滤

        Returns:
            列表，每个元素为 (node_id, distance) 元组
        """
        if len(self.node_ids) == 0:
            logger.warning("No node IDs loaded, returning empty results")
            return []

        top_k = min(top_k, len(self.node_ids))
        
        # 确保 query_emb 是 2D array
        if query_emb.ndim == 1:
            query_emb = query_emb.reshape(1, -1)

        # FAISS 搜索
        D, I = self.index.search(query_emb.astype("float32"), top_k)

        results = []
        for dist, idx in zip(D[0], I[0]):
            if idx < 0 or idx >= len(self.node_ids):
                continue

            # 距离阈值过滤
            if distance_threshold is not None and dist > distance_threshold:
                logger.debug(
                    f"Filtered out node {self.node_ids[idx]} with distance {dist} "
                    f"exceeding threshold {distance_threshold}"
                )
                continue

            logger.debug(
                f"Selected node {self.node_ids[idx]} with distance {dist}"
            )
            results.append((self.node_ids[idx], float(dist)))

        return results

    def search_by_text(
        self,
        query_text: str,
        top_k: int = 5,
        distance_threshold: float | None = None
    ) -> list[tuple[str, float]]:
        """使用文本查询进行搜索（便捷方法）

        Args:
            query_text: 查询文本
            top_k: 返回前 k 个结果
            distance_threshold: 距离阈值

        Returns:
            列表，每个元素为 (node_id, distance) 元组
        """
        query_emb = self.encode(query_text)
        return self.search_similar(query_emb, top_k=top_k, distance_threshold=distance_threshold)

    def get_knowledge(self, node_id: str) -> Any:
        """获取节点的知识内容

        Args:
            node_id: 节点 ID

        Returns:
            节点的内容（格式取决于 nodes_data 的结构）。

        Note:
            为了保持通用性，这里不会强绑定某个字段（例如 improve_knowledge）。
            如需精确指定字段，建议使用 `get_knowledge_by_path()`。
        """
        if not self.nodes_data:
            logger.warning("Nodes data not loaded, cannot retrieve knowledge")
            return None

        node = self.nodes_data.get(str(node_id), {})
        # 兜底：按常见字段尝试提取；都没有就返回整个 node
        for path in self._default_content_candidates():
            val = self._get_by_dotted_path(node, path, default=None)
            if val not in (None, "", [], {}):
                return val
        return node

    def get_knowledge_by_path(self, node_id: str, content_path: str, default: Any = None) -> Any:
        """按点路径提取节点内容字段（通用）。"""
        if not self.nodes_data:
            logger.warning("Nodes data not loaded, cannot retrieve knowledge")
            return default
        node = self.nodes_data.get(str(node_id), {})
        return self._get_by_dotted_path(node, content_path, default=default)

    def get_node_data(self, node_id: str) -> dict | None:
        """获取完整的节点数据

        Args:
            node_id: 节点 ID

        Returns:
            完整的节点数据字典，如果不存在则返回 None
        """
        if not self.nodes_data:
            return None
        return self.nodes_data.get(str(node_id))


def main():
    """命令行接口示例"""
    import argparse

    parser = argparse.ArgumentParser(description="RAG Searcher CLI")
    parser.add_argument("--vec_dir", required=True, help="Vector database directory")
    parser.add_argument("--model", 
                       default="evomaster/skills/rag/local_models/all-mpnet-base-v2",
                       help="Embedding model path, HuggingFace model name, or OpenAI model name (default: local model)")
    parser.add_argument("--nodes_data", help="Nodes data JSON file")
    parser.add_argument(
        "--node_id_key",
        default="node_id",
        help="ID key name in nodes.jsonl per-line JSON (default: node_id)",
    )
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results")
    parser.add_argument("--threshold", type=float, help="Distance threshold")
    parser.add_argument(
        "--content_path",
        default=None,
        help="Dotted path to extract content from nodes_data (e.g. content.text). "
             "If omitted, uses a set of common fallback fields.",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    # OpenAI embedding 参数
    parser.add_argument(
        "--embedding_type",
        choices=["auto", "local", "openai"],
        default="auto",
        help="Embedding type: 'local' for transformer models, 'openai' for OpenAI API, 'auto' to detect (default: auto)",
    )
    parser.add_argument(
        "--embedding_api_key",
        help="OpenAI API key for embedding (can also use OPENAI_EMBEDDING_API_KEY env var)",
    )
    parser.add_argument(
        "--embedding_base_url",
        help="OpenAI API base URL for embedding (can also use OPENAI_EMBEDDING_BASE_URL env var)",
    )
    parser.add_argument(
        "--embedding_dimensions",
        type=int,
        help="Embedding dimensions for text-embedding-3-* models (default: 3072)",
    )

    args = parser.parse_args()

    # 路径解析：evomaster/ 相对项目根
    project_root = _find_project_root()
    vec_dir_resolved = str(_resolve_path(args.vec_dir, project_root))
    nodes_data_resolved = str(_resolve_path(args.nodes_data, project_root)) if args.nodes_data else None
    
    # 仅对本地模型路径进行解析
    model_resolved = args.model
    if args.embedding_type != "openai" and str(args.model).replace("\\", "/").startswith("evomaster/"):
        model_resolved = str(_resolve_path(args.model, project_root))

    # 初始化 searcher
    searcher = RAGSearcher(
        vec_dir=vec_dir_resolved,
        model_name=model_resolved,
        nodes_data_json=nodes_data_resolved,
        node_id_key=args.node_id_key,
        embedding_type=args.embedding_type,
        embedding_api_key=args.embedding_api_key,
        embedding_base_url=args.embedding_base_url,
        embedding_dimensions=args.embedding_dimensions,
    )

    # 搜索
    results = searcher.search_by_text(
        query_text=args.query,
        top_k=args.top_k,
        distance_threshold=args.threshold
    )

    if args.output == "json":
        payload = {
            "query": args.query,
            "results": [
                {
                    "node_id": node_id,
                    "distance": distance,
                    "content": (
                        searcher.get_knowledge_by_path(node_id, args.content_path)
                        if (args.nodes_data and args.content_path)
                        else (searcher.get_knowledge(node_id) if args.nodes_data else None)
                    ),
                }
                for (node_id, distance) in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # text 输出
    print(f"\nSearch results for: '{args.query}'")
    print("=" * 60)
    for i, (node_id, distance) in enumerate(results, 1):
        print(f"\n{i}. Node ID: {node_id}")
        print(f"   Distance: {distance:.4f}")

        if args.nodes_data:
            if args.content_path:
                content = searcher.get_knowledge_by_path(node_id, args.content_path)
            else:
                content = searcher.get_knowledge(node_id)
            if content not in (None, "", [], {}):
                print(f"   Content: {content}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
