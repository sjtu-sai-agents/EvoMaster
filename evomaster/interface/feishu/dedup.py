"""消息去重

内存 dict 实现，支持 TTL 过期和容量上限。
"""

from __future__ import annotations

import threading
import time
import logging

logger = logging.getLogger(__name__)

# 默认参数
_DEFAULT_TTL = 30 * 60  # 30 分钟
_DEFAULT_MAX_SIZE = 1000
_DEFAULT_CLEANUP_INTERVAL = 5 * 60  # 5 分钟


class MessageDedup:
    """消息去重器"""

    def __init__(
        self,
        ttl: float = _DEFAULT_TTL,
        max_size: int = _DEFAULT_MAX_SIZE,
        cleanup_interval: float = _DEFAULT_CLEANUP_INTERVAL,
    ):
        self._store: dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max_size = max_size
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.monotonic()

    def try_record_message(self, message_id: str, scope: str = "default") -> bool:
        """尝试记录消息

        Args:
            message_id: 飞书消息 ID
            scope: 作用域（如 chat_id），用于隔离不同上下文的去重

        Returns:
            True 表示是新消息（已记录），False 表示重复消息
        """
        key = f"{scope}:{message_id}"
        now = time.monotonic()

        with self._lock:
            # 定期清理
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup(now)

            if key in self._store:
                logger.debug("Duplicate message: %s", key)
                return False

            self._store[key] = now

            # 容量溢出时强制清理
            if len(self._store) > self._max_size:
                self._cleanup(now)

            return True

    def _cleanup(self, now: float) -> None:
        """清理过期条目（调用方需持有 _lock）"""
        expired = [k for k, ts in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]

        # 如果仍然超限，按时间排序删除最旧的
        if len(self._store) > self._max_size:
            sorted_keys = sorted(self._store, key=self._store.get)  # type: ignore[arg-type]
            excess = len(self._store) - self._max_size
            for k in sorted_keys[:excess]:
                del self._store[k]

        self._last_cleanup = now
        logger.debug("Dedup cleanup: %d entries remaining", len(self._store))
