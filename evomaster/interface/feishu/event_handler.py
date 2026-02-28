"""飞书事件解析

解析 im.message.receive_v1 事件，提取消息上下文。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FeishuMessageContext:
    """解析后的飞书消息上下文"""

    chat_id: str
    message_id: str
    sender_open_id: str
    chat_type: str  # "p2p" 或 "group"
    content: str  # 纯文本内容
    message_type: str  # "text", "post", 等
    mentions: list[str] | None = None  # 被 @ 的 open_id 列表


def parse_event(event_data) -> Optional[FeishuMessageContext]:
    """从飞书 SDK 事件对象中提取消息上下文

    Args:
        event_data: lark_oapi 事件 data (P2ImMessageReceiveV1Data)

    Returns:
        FeishuMessageContext 或 None（解析失败时）
    """
    try:
        message = event_data.message
        sender = event_data.sender

        chat_id = message.chat_id
        message_id = message.message_id
        message_type = message.message_type
        chat_type = message.chat_type

        sender_open_id = sender.sender_id.open_id if sender and sender.sender_id else ""

        content = parse_message_content(message.content, message_type)

        # 提取 @mention 列表
        mentions = []
        if hasattr(message, "mentions") and message.mentions:
            for mention in message.mentions:
                if hasattr(mention, "id") and mention.id:
                    open_id = getattr(mention.id, "open_id", None)
                    if open_id:
                        mentions.append(open_id)

        return FeishuMessageContext(
            chat_id=chat_id,
            message_id=message_id,
            sender_open_id=sender_open_id,
            chat_type=chat_type,
            content=content,
            message_type=message_type,
            mentions=mentions or None,
        )
    except Exception:
        logger.exception("Failed to parse Feishu event")
        return None


def parse_message_content(raw_content: str, message_type: str) -> str:
    """解析消息内容为纯文本

    Args:
        raw_content: 飞书消息 content JSON 字符串
        message_type: 消息类型

    Returns:
        纯文本内容
    """
    try:
        data = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        return raw_content or ""

    if message_type == "text":
        return data.get("text", "").strip()

    if message_type == "post":
        # post 类型是富文本，提取所有 text 段
        parts: list[str] = []
        # 尝试中英文标题
        title = data.get("title", "")
        if title:
            parts.append(title)

        content_blocks = data.get("content", [])
        for line in content_blocks:
            for element in line:
                tag = element.get("tag", "")
                if tag == "text":
                    parts.append(element.get("text", ""))
                elif tag == "a":
                    parts.append(element.get("text", element.get("href", "")))
                elif tag == "at":
                    # @人的标记，跳过
                    pass
        return "\n".join(parts).strip()

    # 其他类型（图片、文件等）返回类型提示
    return f"[{message_type}]"
