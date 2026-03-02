"""指标解析与安全兜底逻辑。"""

import json
from typing import Any

from .runtime import extract_json_code


def parse_metric_content(text: str) -> dict[str, Any]:
    """尝试解析纯 JSON；失败则视为 bug。"""
    if not text:
        return {"metric": None, "is_bug": True, "error": "empty metric text"}

    cleaned = text.strip()
    try:
        cleaned = extract_json_code(cleaned)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception as e:  # noqa: BLE001
        return {"metric": None, "is_bug": True, "error": f"metric json parse failed: {e}"}

    return {"metric": None, "is_bug": True, "error": "metric content invalid"}
