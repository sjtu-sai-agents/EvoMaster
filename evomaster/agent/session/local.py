"""EvoMaster 本地 Session 实现

在本地直接执行命令，无需容器。
"""

from __future__ import annotations

import threading
from typing import Any

from pydantic import Field

from evomaster.env.local import LocalEnv, LocalEnvConfig

from .base import BaseSession, SessionConfig


class LocalSessionConfig(SessionConfig):
    """本地 Session 配置"""
    encoding: str = Field(default="utf-8", description="文件编码")
    symlinks: dict[str, str] = Field(
        default_factory=dict,
        description="软链接配置，格式：{源目录路径: 工作空间内的目标路径}"
    )
    config_dir: str | None = Field(
        default=None,
        description="配置文件所在目录，用于解析 symlinks 中的相对路径"
    )
    gpu_devices: str | list[str] | None = Field(
        default=None,
        description="GPU 设备，如 '2' 或 ['0', '1']，None 表示不使用 GPU 限制"
    )
    cpu_devices: str | list[int] | None = Field(
        default=None,
        description="CPU 设备，如 '0-15' 或 [0, 1, 2, 3]，None 表示不使用 CPU 限制"
    )
    parallel: dict[str, Any] | None = Field(
        default=None,
        description="并行执行配置，包含 enabled 和 max_parallel 字段"
    )


class LocalSession(BaseSession):
    """本地 Session 实现
    
    在本地直接执行 bash 命令，无需容器。
    内部使用 LocalEnv 来完成底层操作。
    """
    
    # 线程本地存储，用于跟踪每个线程的并行索引
    _thread_local = threading.local()

    def __init__(self, config: LocalSessionConfig | None = None):
        super().__init__(config)
        self.config: LocalSessionConfig = config or LocalSessionConfig()
        # 创建 LocalEnv 实例
        env_config = LocalEnvConfig(session_config=self.config)
        self._env = LocalEnv(env_config)
    
    def set_parallel_index(self, parallel_index: int | None) -> None:
        """设置当前线程的并行索引
        
        Args:
            parallel_index: 并行索引（从 0 开始），None 表示不使用并行资源分配
        """
        self._thread_local.parallel_index = parallel_index
    
    def get_parallel_index(self) -> int | None:
        """获取当前线程的并行索引
        
        Returns:
            并行索引，如果未设置则返回 None
        """
        return getattr(self._thread_local, 'parallel_index', None)
    
    def set_workspace_path(self, workspace_path: str | None) -> None:
        """设置当前线程的工作空间路径（用于 split_workspace_for_exp）
        
        Args:
            workspace_path: 工作空间路径，None 表示使用默认工作空间
        """
        self._thread_local.workspace_path = workspace_path
    
    def get_workspace_path(self) -> str | None:
        """获取当前线程的工作空间路径
        
        Returns:
            工作空间路径，如果未设置则返回 None（使用默认工作空间）
        """
        return getattr(self._thread_local, 'workspace_path', None)
        
    def open(self) -> None:
        """打开本地会话"""
        if self._is_open:
            self.logger.warning("Session already open")
            return
        
        # 使用 LocalEnv 来设置环境
        if not self._env.is_ready:
            self._env.setup()
        
        self._is_open = True
        self.logger.info("Local session opened")

    def close(self) -> None:
        """关闭本地会话"""
        if not self._is_open:
            return
        
        # 使用 LocalEnv 来清理环境
        if self._env.is_ready:
            self._env.teardown()
        
        self._is_open = False
        self.logger.info("Session closed")

    def exec_bash(
        self,
        command: str,
        timeout: int | None = None,
        is_input: bool = False,
        parallel_index: int | None = None,
    ) -> dict[str, Any]:
        """执行 bash 命令
        
        提供本地命令执行能力。
        
        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）
            is_input: 是否是向正在运行的进程发送输入（本地不支持）
            parallel_index: 并行索引（可选，如果未提供则从线程本地存储获取）
        """
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        timeout = timeout or self.config.timeout
        command = command.strip()
        
        # 本地环境不支持 is_input 模式
        if is_input:
            return {
                "stdout": "ERROR: Local session does not support is_input mode.",
                "stderr": "",
                "exit_code": 1,
            }
        
        # 获取并行索引（优先使用参数，否则从线程本地存储获取）
        if parallel_index is None:
            parallel_index = self.get_parallel_index()
        
        # 获取线程本地的工作空间路径（用于 split_workspace_for_exp）
        workspace_override = self.get_workspace_path()
        
        # 使用 LocalEnv 执行命令
        result = self._env.local_exec(
            command, timeout=timeout,
            workdir=workspace_override,
            parallel_index=parallel_index,
        )
        
        # 获取工作目录（优先使用线程本地的工作空间路径）
        workspace = workspace_override or self.config.workspace_path
        
        # 构建结果
        return {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", -1),
            "working_dir": workspace,
            "output": result.get("output", ""),
        }

    def upload(self, local_path: str, remote_path: str) -> None:
        """上传文件到本地环境"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        self._env.upload_file(local_path, remote_path)

    def read_file(self, remote_path: str, encoding: str = "utf-8") -> str:
        """读取远程文件内容（文本）"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        return self._env.read_file_content(remote_path, encoding)
    
    def write_file(self, remote_path: str, content: str, encoding: str = "utf-8") -> None:
        """写入内容到远程文件"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        self._env.write_file_content(remote_path, content, encoding)
    
    def download(self, remote_path: str, timeout: int | None = None) -> bytes:
        """从本地环境下载文件"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        return self._env.download_file(remote_path, timeout)
    
    def path_exists(self, remote_path: str) -> bool:
        """检查远程路径是否存在"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        return self._env.path_exists(remote_path)
    
    def is_file(self, remote_path: str) -> bool:
        """检查远程路径是否是文件"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        return self._env.is_file(remote_path)
    
    def is_directory(self, remote_path: str) -> bool:
        """检查远程路径是否是目录"""
        if not self._is_open:
            raise RuntimeError("Session not open")
        
        return self._env.is_directory(remote_path)
