"""FeishuBot 主类

生命周期管理：初始化 → 接收事件 → 解析 → 去重 → 调度 → 返回结果。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1, P2ImMessageMessageReadV1

from .client import create_feishu_client
from .config import FeishuBotConfig
from .dedup import MessageDedup
from .dispatcher import TaskDispatcher
from .event_handler import parse_event
from .sender import send_card_message, send_text_message

logger = logging.getLogger(__name__)

# 超过此长度使用卡片消息（支持更长内容和 Markdown）
_CARD_THRESHOLD = 2000

# /agent <name> <task> 命令正则
_COMMAND_RE = re.compile(r"^/agent\s+(\S+)\s+(.+)$", re.DOTALL)


class FeishuBot:
    """飞书 Bot 主类"""

    def __init__(
        self,
        config: FeishuBotConfig,
        project_root: str | Path,
    ):
        """
        Args:
            config: 飞书 Bot 配置
            project_root: EvoMaster 项目根目录
        """
        self._config = config
        self._project_root = Path(project_root)

        # 创建飞书 Client
        self._client = create_feishu_client(
            app_id=config.app_id,
            app_secret=config.app_secret,
            domain=config.domain,
        )

        # 消息去重
        self._dedup = MessageDedup()

        # 任务调度器
        self._dispatcher = TaskDispatcher(
            project_root=self._project_root,
            default_agent=config.default_agent,
            default_config_path=config.default_config_path,
            max_workers=config.max_concurrent_tasks,
            task_timeout=config.task_timeout,
            on_result=self._send_result,
        )

        self._ws_client: Optional[lark.ws.Client] = None

    def _handle_message_event(self, data: P2ImMessageReceiveV1) -> None:
        """处理收到的消息事件"""
        ctx = parse_event(data.event)
        if ctx is None:
            logger.warning("Failed to parse event, skipping")
            return

        # 去重
        if not self._dedup.try_record_message(ctx.message_id, scope=ctx.chat_id):
            return

        # 权限检查
        if self._config.allow_from and ctx.sender_open_id not in self._config.allow_from:
            logger.info("Message from unauthorized user: %s", ctx.sender_open_id)
            send_text_message(
                self._client,
                ctx.chat_id,
                "抱歉，您没有权限使用此 Bot。",
                reply_to_message_id=ctx.message_id,
            )
            return

        # 群聊场景：仅处理 @Bot 的消息
        if ctx.chat_type == "group" and not ctx.mentions:
            logger.debug("Ignoring group message without @mention: %s", ctx.message_id)
            return

        # 忽略非文本消息
        if ctx.message_type not in ("text", "post"):
            logger.debug("Ignoring non-text message: %s", ctx.message_type)
            return

        # 解析命令
        agent_name, task_text = self._parse_command(ctx.content)

        if not task_text.strip():
            send_text_message(
                self._client,
                ctx.chat_id,
                "请提供任务描述。用法：直接发送任务，或使用 /agent <agent名称> <任务描述>",
                reply_to_message_id=ctx.message_id,
            )
            return

        # 发送确认消息
        agent_label = agent_name or self._config.default_agent
        send_text_message(
            self._client,
            ctx.chat_id,
            f"任务已接收，正在使用 [{agent_label}] 处理...\n任务: {task_text[:200]}",
            reply_to_message_id=ctx.message_id,
        )

        # 调度任务
        self._dispatcher.dispatch(
            chat_id=ctx.chat_id,
            message_id=ctx.message_id,
            task_text=task_text,
            agent_name=agent_name,
        )

    def _handle_message_read_event(self, data: P2ImMessageMessageReadV1) -> None:
        """处理消息已读事件（忽略，仅注册以避免 SDK 报错）"""
        pass

    def _parse_command(self, text: str) -> tuple[Optional[str], str]:
        """解析命令前缀

        支持格式：
            /agent <name> <task>    → (name, task)
            <task>                  → (None, task)

        Returns:
            (agent_name, task_text)
        """
        match = _COMMAND_RE.match(text.strip())
        if match:
            return match.group(1), match.group(2).strip()
        return None, text

    def _send_result(self, chat_id: str, message_id: str, result_text: str) -> None:
        """结果回调：发送结果到飞书

        短文本用普通文本消息，长文本用卡片消息（支持 Markdown）。
        """
        if len(result_text) > _CARD_THRESHOLD:
            # 超长内容使用卡片消息
            send_card_message(
                self._client,
                chat_id,
                title="任务完成",
                content=result_text,
                reply_to_message_id=message_id,
            )
        else:
            send_text_message(
                self._client,
                chat_id,
                result_text,
                reply_to_message_id=message_id,
            )

    def start(self) -> None:
        """启动 Bot（阻塞式）

        当前支持 WebSocket 模式。
        """
        logger.info(
            "Starting FeishuBot: agent=%s, mode=%s",
            self._config.default_agent,
            self._config.connection_mode,
        )

        # 构建事件处理器
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .register_p2_im_message_message_read_v1(self._handle_message_read_event)
            .build()
        )

        if self._config.connection_mode == "websocket":
            self._ws_client = (
                lark.ws.Client(
                    self._config.app_id,
                    self._config.app_secret,
                    event_handler=event_handler,
                    log_level=lark.LogLevel.INFO,
                )
            )
            logger.info("FeishuBot is running via WebSocket. Press Ctrl+C to stop.")
            self._ws_client.start()
        else:
            raise ValueError(
                f"Unsupported connection mode: {self._config.connection_mode}. "
                "Currently only 'websocket' is supported."
            )

    def stop(self) -> None:
        """停止 Bot

        等待正在执行的任务完成后再关闭（最多等 task_timeout 秒）。
        """
        logger.info("Stopping FeishuBot, waiting for active tasks to finish...")
        self._dispatcher.shutdown(wait=True)

        if self._ws_client is not None:
            try:
                # lark-oapi ws.Client 底层是 daemon 线程，进程退出时自动终止
                # 如果未来 SDK 提供 stop/close 方法，在此调用
                logger.debug("WebSocket client reference cleared")
            except Exception as e:
                logger.warning("Error cleaning up WebSocket client: %s", e)
            finally:
                self._ws_client = None

        logger.info("FeishuBot stopped")
