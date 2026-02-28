"""Feishu SDK Client 工厂

创建并缓存 lark_oapi.Client 实例。
"""

from __future__ import annotations

import logging
from typing import Dict

import lark_oapi as lark

logger = logging.getLogger(__name__)

# 缓存：key = (app_id, domain) → Client
_client_cache: Dict[str, lark.Client] = {}


def create_feishu_client(
    app_id: str,
    app_secret: str,
    domain: str = "https://open.feishu.cn",
) -> lark.Client:
    """创建或获取缓存的飞书 Client

    Args:
        app_id: 飞书应用 App ID
        app_secret: 飞书应用 App Secret
        domain: 飞书 API 域名

    Returns:
        lark_oapi.Client 实例
    """
    cache_key = f"{app_id}@{domain}"

    if cache_key in _client_cache:
        logger.debug("Reusing cached Feishu client: %s", cache_key)
        return _client_cache[cache_key]

    # 域名 → lark domain 常量映射
    domain_map = {
        "https://open.feishu.cn": lark.FEISHU_DOMAIN,
        "https://open.larksuite.com": lark.LARK_DOMAIN,
    }
    lark_domain = domain_map.get(domain, domain)

    client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .domain(lark_domain)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )

    _client_cache[cache_key] = client
    logger.info("Created Feishu client: %s", cache_key)
    return client
