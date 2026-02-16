#!/usr/bin/env python3
"""Text Encoder - 文本编码工具

提供独立的文本编码功能，将文本转换为向量。
支持本地 transformer 模型和 OpenAI embedding API。
"""

import logging
import os
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


# 从 search.py 导入 Embedder 相关类
from search import create_embedder, BaseEmbedder


class TextEncoder:
    """文本编码器，支持本地模型和 OpenAI API"""

    def __init__(
        self,
        model_name: str = "evomaster/skills/rag/local_models/all-mpnet-base-v2",
        device: str = "cpu",
        embedding_type: str = "auto",
        embedding_api_key: str | None = None,
        embedding_base_url: str | None = None,
        embedding_dimensions: int | None = None,
    ):
        """初始化编码器

        Args:
            model_name: 模型名称或路径
            device: 计算设备 ('cpu' 或 'cuda')，仅本地模型使用
            embedding_type: "local", "openai", 或 "auto"（自动检测）
            embedding_api_key: OpenAI API key（仅 openai 类型需要）
            embedding_base_url: OpenAI API base URL（仅 openai 类型需要）
            embedding_dimensions: Embedding 维度（仅 openai 的 text-embedding-3-* 支持）
        """
        self.model_name = model_name
        self.device = device
        
        # 使用统一的 embedder 创建函数
        self.embedder = create_embedder(
            model=model_name,
            embedding_type=embedding_type,
            api_key=embedding_api_key,
            base_url=embedding_base_url,
            dimensions=embedding_dimensions,
            device=device,
        )
        logger.info(f"Initialized encoder with model: {model_name}")

    def encode(
        self,
        text: str,
        max_length: int = 512,
        normalize: bool = False
    ) -> np.ndarray:
        """编码文本

        Args:
            text: 输入文本
            max_length: 最大长度（仅本地模型使用）
            normalize: 是否归一化向量

        Returns:
            编码后的向量
        """
        emb = self.embedder.encode(text)
        
        # 确保是 1D 向量
        if emb.ndim > 1:
            emb = emb[0]

        # 归一化（可选）
        if normalize:
            norm = np.linalg.norm(emb)
            emb = emb / (norm + 1e-8)

        return emb

    def encode_batch(
        self,
        texts: list[str],
        max_length: int = 512,
        normalize: bool = False,
        batch_size: int = 32
    ) -> np.ndarray:
        """批量编码文本

        Args:
            texts: 文本列表
            max_length: 最大长度（仅本地模型使用）
            normalize: 是否归一化向量
            batch_size: 批处理大小

        Returns:
            编码后的向量数组 (n_texts, embedding_dim)
        """
        all_embeddings = []

        for text in texts:
            emb = self.encode(text, max_length=max_length, normalize=normalize)
            all_embeddings.append(emb)

        return np.vstack(all_embeddings)


def main():
    """命令行接口"""
    import argparse

    parser = argparse.ArgumentParser(description="Text Encoder CLI")
    parser.add_argument("--model", 
                       default="evomaster/skills/rag/local_models/all-mpnet-base-v2",
                       help="Embedding model path, HuggingFace model name, or OpenAI model name (default: local model)")
    parser.add_argument("--text", help="Text to encode")
    parser.add_argument("--file", help="File containing text (one per line)")
    parser.add_argument("--output", help="Output file for embeddings (.npy)")
    parser.add_argument("--max_length", type=int, default=512, help="Max length")
    parser.add_argument("--normalize", action="store_true", help="Normalize vectors")
    parser.add_argument("--batch_size", type=int, default=32, help="Batch size")
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

    # 初始化编码器
    encoder = TextEncoder(
        model_name=args.model,
        embedding_type=args.embedding_type,
        embedding_api_key=args.embedding_api_key,
        embedding_base_url=args.embedding_base_url,
        embedding_dimensions=args.embedding_dimensions,
    )

    # 读取文本
    if args.text:
        texts = [args.text]
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            texts = [line.strip() for line in f if line.strip()]
    else:
        # 从 stdin 读取
        texts = [line.strip() for line in sys.stdin if line.strip()]

    if not texts:
        print("Error: No text provided", file=sys.stderr)
        sys.exit(1)

    # 编码
    if len(texts) == 1:
        embedding = encoder.encode(texts[0], max_length=args.max_length, normalize=args.normalize)
    else:
        embedding = encoder.encode_batch(
            texts,
            max_length=args.max_length,
            normalize=args.normalize,
            batch_size=args.batch_size
        )

    # 输出
    if args.output:
        np.save(args.output, embedding)
        print(f"Saved embeddings to {args.output}")
    else:
        # 输出到 stdout（以可读格式）
        print(f"Embedding shape: {embedding.shape}")
        print(f"Embedding:\n{embedding}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
