"""RAG 相关工具：解析 Plan 输出、提取 Agent 回答、数据库参数、更新 prompt 占位符"""

import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_VEC_DIR = "evomaster/skills/rag/MLE_DATABASE/node_vectorstore/draft"
DEFAULT_NODES_DATA = "evomaster/skills/rag/MLE_DATABASE/node_vectorstore/draft/draft_407_75_db.json"
DEFAULT_MODEL = "evomaster/skills/rag/local_models/all-mpnet-base-v2"

# 全局 embedding 配置（由 playground 设置）
_embedding_config: dict | None = None


def set_embedding_config(config: dict | None) -> None:
    """设置全局 embedding 配置（由 playground 调用）"""
    global _embedding_config
    _embedding_config = config


def get_embedding_config() -> dict | None:
    """获取全局 embedding 配置"""
    return _embedding_config


def _project_root() -> Path:
    """项目根目录（含 evomaster/、playground/；从 rag_utils 上三级到 core 再上两级）"""
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _resolve_db_path(path_str: str, root: Path) -> str:
    """将相对路径（如 evomaster/...）转为绝对路径；已是绝对路径则返回原样。"""
    if not path_str or not path_str.strip():
        return path_str
    p = Path(path_str.strip().replace("\\", "/"))
    if p.is_absolute():
        return str(p.resolve())
    return str((root / p).resolve())


def resolve_db_to_absolute_paths(db: dict, project_root: Path | None = None) -> dict:
    """将 db 中的 vec_dir、nodes_data、model 转为绝对路径（便于 RAG 与各 Agent 使用）。"""
    root = project_root or _project_root()
    result = {
        "vec_dir": _resolve_db_path(db["vec_dir"], root),
        "nodes_data": _resolve_db_path(db["nodes_data"], root),
        "model": _resolve_db_path(db["model"], root),
    }
    
    # 添加 embedding 配置参数
    embedding_config = get_embedding_config()
    if embedding_config:
        emb_type = embedding_config.get("type", "local")
        result["embedding_type"] = emb_type
        
        if emb_type == "openai":
            openai_cfg = embedding_config.get("openai", {})
            result["model"] = openai_cfg.get("model", "text-embedding-3-large")
            result["embedding_dimensions"] = openai_cfg.get("dimensions")
        else:
            local_cfg = embedding_config.get("local", {})
            result["model"] = _resolve_db_path(
                local_cfg.get("model", DEFAULT_MODEL), root
            )
            result["embedding_type"] = "local"
    
    return result


def parse_plan_output(text: str) -> dict:
    """从 Plan Agent 输出中解析 query、top_k、threshold"""
    out = {"query": "", "top_k": 5, "threshold": 1.5}
    if not text:
        return out
    q = re.search(r"query\s*[：:]\s*(.+?)(?=\s*(?:top_k|threshold)|$)", text, re.DOTALL | re.IGNORECASE)
    if q:
        out["query"] = q.group(1).strip().strip('"\'')
    k = re.search(r"top_k\s*[：:]\s*(\d+)", text, re.IGNORECASE)
    if k:
        out["top_k"] = int(k.group(1))
    t = re.search(r"threshold\s*[：:]\s*([\d.]+)", text, re.IGNORECASE)
    if t:
        out["threshold"] = float(t.group(1))
    return out


def extract_agent_response(trajectory: Any) -> str:
    """从轨迹中提取 Agent 的最终回答。若 Agent 用 finish 结束，取 finish 的 message；否则取最后一条 assistant content。"""
    if not trajectory or not trajectory.dialogs:
        return ""
    last_dialog = trajectory.dialogs[-1]
    for message in reversed(last_dialog.messages):
        if not (hasattr(message, "role") and getattr(message.role, "value", message.role) == "assistant"):
            continue
        # 若该条 assistant 调用了 finish，优先用 finish 的 message 作为回答
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                fn = getattr(tc, "function", tc) if hasattr(tc, "function") else tc
                name = getattr(fn, "name", None) or (fn.get("name") if isinstance(fn, dict) else None)
                if name == "finish":
                    args = getattr(fn, "arguments", None) or (fn.get("arguments", "{}") if isinstance(fn, dict) else "{}")
                    try:
                        obj = json.loads(args) if isinstance(args, str) else args
                        if isinstance(obj, dict) and "message" in obj:
                            return obj["message"]
                    except (json.JSONDecodeError, TypeError):
                        pass
        if hasattr(message, "content") and message.content:
            return message.content
    return ""


def get_db_from_description(description: str) -> dict:
    """从任务描述中解析数据库参数，未出现则用默认值（相对路径）。"""
    db = {
        "vec_dir": DEFAULT_VEC_DIR,
        "nodes_data": DEFAULT_NODES_DATA,
        "model": DEFAULT_MODEL,
        # 默认 embedding 参数（会被 resolve_db_to_absolute_paths 覆盖/补全）
        "embedding_type": "local",
        "embedding_dimensions": "",
    }
    if "vec_dir:" in description:
        m = re.search(r"vec_dir:\s*(\S+)", description)
        if m:
            db["vec_dir"] = m.group(1).strip()
    if "nodes_data:" in description:
        m = re.search(r"nodes_data:\s*(\S+)", description)
        if m:
            db["nodes_data"] = m.group(1).strip()
    if "model:" in description:
        m = re.search(r"model:\s*(\S+)", description)
        if m:
            db["model"] = m.group(1).strip()
    return db


def update_agent_format_kwargs(agent, **kwargs) -> None:
    """更新 agent 的 prompt_format_kwargs（用于 user prompt 占位符）"""
    if hasattr(agent, "_prompt_format_kwargs"):
        agent._prompt_format_kwargs.update(kwargs)
