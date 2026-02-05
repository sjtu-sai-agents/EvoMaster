"""EvoMaster Env 基类

Env 是环境组件，负责管理执行环境和作业调度。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession, SessionConfig


class EnvConfig(BaseModel):
    """Env 基础配置"""
    name: str = Field(default="default_env", description="环境名称")
    session_config: SessionConfig | None = Field(default=None, description="Session 配置")


class BaseEnv(ABC):
    """Env 抽象基类

    定义环境组件的标准接口：
    - Session 管理
    - 作业执行
    - 资源管理
    """

    def __init__(self, config: EnvConfig | None = None):
        """初始化 Env

        Args:
            config: Env 配置
        """
        self.config = config or EnvConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._is_ready = False

    @property
    def is_ready(self) -> bool:
        """环境是否已准备就绪"""
        return self._is_ready

    @abstractmethod
    def setup(self) -> None:
        """初始化环境"""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """清理环境资源"""
        pass

    @abstractmethod
    def get_session(self) -> BaseSession:
        """获取 Session 用于执行命令

        Returns:
            BaseSession 实例
        """
        pass

    @abstractmethod
    def submit_job(
        self,
        command: str,
        job_type: str = "debug",
        **kwargs: Any,
    ) -> str:
        """提交作业到环境

        Args:
            command: 要执行的命令
            job_type: 作业类型（"debug" 或 "train"）
            **kwargs: 额外参数

        Returns:
            作业 ID
        """
        pass

    @abstractmethod
    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """查询作业状态

        Args:
            job_id: 作业 ID

        Returns:
            状态信息字典
        """
        pass

    @abstractmethod
    def cancel_job(self, job_id: str) -> None:
        """取消作业

        Args:
            job_id: 作业 ID
        """
        pass

    def __enter__(self) -> BaseEnv:
        """上下文管理器入口"""
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.teardown()
