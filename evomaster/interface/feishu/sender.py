"""飞书消息发送

发送文本消息、卡片消息和回复消息到飞书。
"""

from __future__ import annotations

import json
import logging

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

logger = logging.getLogger(__name__)

# 卡片消息内容上限（飞书 interactive 消息约 30KB，保守取 15KB）
_MAX_CARD_CONTENT_LENGTH = 15000


def send_text_message(
    client: lark.Client,
    chat_id: str,
    text: str,
    reply_to_message_id: str | None = None,
) -> bool:
    """发送或回复文本消息

    Args:
        client: 飞书 Client 实例
        chat_id: 聊天 ID
        text: 消息文本
        reply_to_message_id: 要回复的消息 ID（可选）

    Returns:
        True 表示发送成功
    """
    content = json.dumps({"text": text})

    try:
        if reply_to_message_id:
            # 回复消息
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_to_message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(content)
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.reply(request)
        else:
            # 发送新消息
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(content)
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.create(request)

        if not response.success():
            logger.error(
                "Failed to send message: code=%s, msg=%s",
                response.code,
                response.msg,
            )
            return False

        logger.debug("Message sent to chat %s", chat_id)
        return True

    except Exception:
        logger.exception("Error sending message to chat %s", chat_id)
        return False


def send_card_message(
    client: lark.Client,
    chat_id: str,
    title: str,
    content: str,
    reply_to_message_id: str | None = None,
) -> bool:
    """发送卡片消息（支持 Markdown 格式，适合较长内容）

    Args:
        client: 飞书 Client 实例
        chat_id: 聊天 ID
        title: 卡片标题
        content: 卡片内容（支持飞书 Markdown 子集）
        reply_to_message_id: 要回复的消息 ID（可选）

    Returns:
        True 表示发送成功
    """
    # 截断超长内容
    if len(content) > _MAX_CARD_CONTENT_LENGTH:
        content = content[:_MAX_CARD_CONTENT_LENGTH] + "\n\n...(内容过长已截断)"

    card = json.dumps({
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "elements": [
            {"tag": "markdown", "content": content},
        ],
    })

    try:
        if reply_to_message_id:
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_to_message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("interactive")
                    .content(card)
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.reply(request)
        else:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(card)
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.create(request)

        if not response.success():
            logger.error(
                "Failed to send card message: code=%s, msg=%s",
                response.code,
                response.msg,
            )
            return False

        logger.debug("Card message sent to chat %s", chat_id)
        return True

    except Exception:
        logger.exception("Error sending card message to chat %s", chat_id)
        return False
