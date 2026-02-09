"""Bohrium 鉴权与 MCP calculation 用 storage/executor 配置。

供 MCP calculation path adaptor 使用，统一从环境变量（.env）读取 BOHRIUM_*，
生成 HTTPS storage 与注入 executor 的鉴权信息。与 _tmp/MatMaster 的 private_callback 对齐。
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict


def get_bohrium_credentials() -> Dict[str, Any]:
    """从环境变量读取 Bohrium 鉴权（.env 或 os.environ）。"""
    access_key = os.getenv("BOHRIUM_ACCESS_KEY", "").strip()
    try:
        project_id = int(os.getenv("BOHRIUM_PROJECT_ID", "-1"))
    except (TypeError, ValueError):
        project_id = -1
    try:
        user_id = int(os.getenv("BOHRIUM_USER_ID", "-1"))
    except (TypeError, ValueError):
        user_id = -1
    return {
        "access_key": access_key,
        "project_id": project_id,
        "user_id": user_id,
    }


def get_bohrium_storage_config() -> Dict[str, Any]:
    """MCP calculation 用 HTTPS storage（type https + Bohrium plugin）。"""
    cred = get_bohrium_credentials()
    return {
        "type": "https",
        "plugin": {
            "type": "bohrium",
            "access_key": cred["access_key"],
            "project_id": cred["project_id"],
            "app_key": "agent",
        },
    }


def inject_bohrium_executor(executor_template: Dict[str, Any]) -> Dict[str, Any]:
    """深拷贝 executor 模板并注入 BOHRIUM_* 鉴权（与 MatMaster private_callback 一致）。"""
    executor = copy.deepcopy(executor_template)
    cred = get_bohrium_credentials()
    if executor.get("type") == "dispatcher":
        rp = executor.setdefault("machine", {}).setdefault("remote_profile", {})
        rp["access_key"] = cred["access_key"]
        rp["project_id"] = cred["project_id"]
        rp["real_user_id"] = cred["user_id"]
        resources = executor.setdefault("resources", {})
        envs = resources.setdefault("envs", {})
        envs["BOHRIUM_PROJECT_ID"] = cred["project_id"]
    return executor
