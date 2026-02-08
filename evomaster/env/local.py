"""本地环境实现

提供本地环境的底层操作接口。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import Field

from .base import BaseEnv, EnvConfig
from evomaster.agent.session.base import SessionConfig


class LocalEnvConfig(EnvConfig):
    """本地环境配置"""
    session_config: SessionConfig = Field(
        ...,
        description="Session 配置"
    )


class LocalEnv(BaseEnv):
    """本地环境实现

    提供本地环境的底层操作接口：
    - 命令执行
    - 文件操作
    - 工作空间管理
    """

    def __init__(self, config: LocalEnvConfig | None = None):
        """初始化本地环境

        Args:
            config: 本地环境配置
        """
        if config is None:
            raise ValueError("LocalEnv requires LocalEnvConfig with session_config")
        super().__init__(config)
        self.config: LocalEnvConfig = config

    def setup(self) -> None:
        """初始化本地环境"""
        if self._is_ready:
            self.logger.warning("Environment already setup")
            return

        self.logger.info("Setting up local environment")
        
        # 确保工作目录存在
        workspace = Path(self.config.session_config.workspace_path)
        workspace.mkdir(parents=True, exist_ok=True)
        
        # 创建软链接（如果有配置）
        session_config = self.config.session_config
        if hasattr(session_config, 'symlinks') and session_config.symlinks:
            self._create_symlinks(workspace, session_config.symlinks)
        
        self._is_ready = True
        self.logger.info("Local environment setup complete")

    def teardown(self) -> None:
        """清理本地环境资源"""
        if not self._is_ready:
            return

        self.logger.info("Tearing down local environment")
        self._is_ready = False
        self.logger.info("Local environment teardown complete")

    def get_session(self) -> Any:
        """获取 Session（LocalEnv 不直接提供 Session，由调用方管理）"""
        raise NotImplementedError("LocalEnv does not provide session directly")

    def submit_job(
        self,
        command: str,
        job_type: str = "debug",
        **kwargs: Any,
    ) -> str:
        """提交作业（LocalEnv 不直接支持作业调度）"""
        raise NotImplementedError("LocalEnv does not support job submission")

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """查询作业状态（LocalEnv 不直接支持作业调度）"""
        raise NotImplementedError("LocalEnv does not support job status")

    def cancel_job(self, job_id: str) -> None:
        """取消作业（LocalEnv 不直接支持作业调度）"""
        raise NotImplementedError("LocalEnv does not support job cancellation")

    def _create_symlinks(self, workspace: Path, symlinks: dict[str, str]) -> None:
        """创建软链接
        
        Args:
            workspace: 工作空间路径
            symlinks: 软链接配置，格式：{源目录路径: 工作空间内的目标路径}
        """
        # 获取项目根目录，用于解析相对路径
        # 优先从配置文件目录向上查找项目根目录（包含 evomaster 目录的目录）
        project_root = None
        if hasattr(self.config.session_config, 'config_dir') and self.config.session_config.config_dir:
            config_dir = Path(self.config.session_config.config_dir)
            # 从配置文件目录向上查找项目根目录
            current = config_dir.resolve()
            while current != current.parent:
                if (current / "evomaster").exists() and (current / "evomaster").is_dir():
                    project_root = current
                    break
                current = current.parent
        
        # 如果没找到项目根目录，尝试使用当前工作目录
        if project_root is None:
            current = Path.cwd()
            while current != current.parent:
                if (current / "evomaster").exists() and (current / "evomaster").is_dir():
                    project_root = current
                    break
                current = current.parent
        
        for source_dir, target_rel_path in symlinks.items():
            # 解析源路径：如果是相对路径，则相对于项目根目录解析；如果是绝对路径，则直接使用
            source_path = Path(source_dir)
            if not source_path.is_absolute():
                # 相对路径：如果找到了项目根目录，则相对于项目根目录；否则相对于当前工作目录
                if project_root is not None:
                    source_path = (project_root / source_dir).resolve()
                    self.logger.debug(f"相对路径 '{source_dir}' 解析为: {source_path} (相对于项目根目录 {project_root})")
                else:
                    source_path = Path(source_dir).resolve()
                    self.logger.debug(f"相对路径 '{source_dir}' 解析为: {source_path} (相对于当前工作目录)")
            else:
                # 绝对路径：直接使用
                source_path = source_path.resolve()
                self.logger.debug(f"绝对路径 '{source_dir}' 解析为: {source_path}")
            
            if not source_path.exists():
                self.logger.warning(f"源目录不存在，跳过软链接: {source_dir} (解析后: {source_path})")
                continue
            
            if not source_path.is_dir():
                self.logger.warning(f"源路径不是目录，跳过软链接: {source_dir} (解析后: {source_path})")
                continue
            
            # 目标路径是相对于工作空间的
            target_path = workspace / target_rel_path
            
            # 如果目标路径已存在，先删除（可能是之前的软链接或文件）
            if target_path.exists() or target_path.is_symlink():
                if target_path.is_symlink():
                    target_path.unlink()
                    self.logger.debug(f"删除已存在的软链接: {target_path}")
                else:
                    # 如果是目录，需要递归删除
                    shutil.rmtree(target_path)
                    self.logger.debug(f"删除已存在的目录: {target_path}")
            
            # 确保目标路径的父目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建目标目录（如果不存在）
            target_path.mkdir(parents=True, exist_ok=True)
            
            # 将源目录下的所有内容链接到目标目录
            self._link_directory_contents(source_path, target_path)
            self.logger.info(f"创建软链接: {source_dir} 下的内容 -> {target_path}")
    
    def _link_directory_contents(self, source_dir: Path, target_dir: Path) -> None:
        """将源目录下的所有内容链接到目标目录
        
        Args:
            source_dir: 源目录路径
            target_dir: 目标目录路径
        """
        for item in source_dir.iterdir():
            source_item = source_dir / item.name
            target_item = target_dir / item.name
            
            # 如果目标已存在，跳过
            if target_item.exists() or target_item.is_symlink():
                self.logger.debug(f"目标已存在，跳过: {target_item}")
                continue
            
            try:
                os.symlink(source_item, target_item)
                self.logger.debug(f"创建软链接: {source_item} -> {target_item}")
            except OSError as e:
                self.logger.warning(f"创建软链接失败: {source_item} -> {target_item}, 错误: {e}")

    def local_exec(
        self,
        command: str,
        timeout: int | None = None,
        workdir: str | None = None,
    ) -> dict[str, Any]:
        """在本地执行命令

        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）
            workdir: 工作目录

        Returns:
            执行结果字典，包含：
            - stdout: 标准输出
            - stderr: 标准错误
            - exit_code: 退出码
            - output: stdout + stderr 的组合
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        timeout = timeout or self.config.session_config.timeout
        workdir = workdir or self.config.session_config.workspace_path

        # 检查工作目录是否存在
        workspace = Path(workdir)
        cwd = workdir if workspace.exists() else None

        # 获取 GPU 和 CPU 配置
        session_config = self.config.session_config
        gpu_devices = getattr(session_config, 'gpu_devices', None)
        cpu_devices = getattr(session_config, 'cpu_devices', None)

        # 构建环境变量
        env = os.environ.copy()
        
        # 设置 GPU 设备
        if gpu_devices is not None:
            if isinstance(gpu_devices, str):
                # 单个 GPU 或 "all"
                env['CUDA_VISIBLE_DEVICES'] = gpu_devices
            elif isinstance(gpu_devices, list):
                # GPU 列表，如 ["0", "1"]
                env['CUDA_VISIBLE_DEVICES'] = ",".join(str(gpu) for gpu in gpu_devices)
            self.logger.debug(f"Setting CUDA_VISIBLE_DEVICES={env.get('CUDA_VISIBLE_DEVICES')}")

        # 构建 CPU 限制命令前缀
        cpu_prefix = ""
        if cpu_devices is not None and sys.platform != "win32":
            if isinstance(cpu_devices, str):
                # CPU 范围字符串，如 "0-15"
                cpu_prefix = f"taskset -c {cpu_devices} "
            elif isinstance(cpu_devices, list):
                # CPU 列表，如 [0, 1, 2, 3]
                cpu_list_str = ",".join(str(cpu) for cpu in cpu_devices)
                cpu_prefix = f"taskset -c {cpu_list_str} "
            self.logger.debug(f"Using CPU prefix: {cpu_prefix}")

        # 组合命令
        final_command = f"{cpu_prefix}{command}" if cpu_prefix else command

        try:
            result = subprocess.run(
                final_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "output": result.stdout + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
                "output": f"Command timed out after {timeout}s",
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "output": str(e),
            }

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """上传文件到本地环境

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径（本地环境中的路径）
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        local_file = Path(local_path)
        remote_file = Path(remote_path)

        if not local_file.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        # 创建远程目录
        remote_file.parent.mkdir(parents=True, exist_ok=True)

        if local_file.is_file():
            shutil.copy2(local_file, remote_file)
            self.logger.debug(f"Uploaded file {local_path} to {remote_path}")
        elif local_file.is_dir():
            shutil.copytree(local_file, remote_file, dirs_exist_ok=True)
            self.logger.debug(f"Uploaded directory {local_path} to {remote_path}")

    def download_file(self, remote_path: str, timeout: int | None = None) -> bytes:
        """从本地环境下载文件

        Args:
            remote_path: 远程文件路径（本地环境中的路径）
            timeout: 超时时间（本地不使用）

        Returns:
            文件内容（字节）
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        remote_file = Path(remote_path)

        if not remote_file.exists():
            raise FileNotFoundError(f"Remote file not found: {remote_path}")

        if not remote_file.is_file():
            raise IsADirectoryError(f"Remote path is not a file: {remote_path}")

        with open(remote_file, "rb") as f:
            return f.read()

    def read_file_content(self, remote_path: str, encoding: str = "utf-8") -> str:
        """读取远程文件内容（文本）

        Args:
            remote_path: 远程文件路径（本地环境中的路径）
            encoding: 文件编码

        Returns:
            文件内容（字符串）
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        remote_file = Path(remote_path)

        if not remote_file.exists():
            raise FileNotFoundError(f"Remote file not found: {remote_path}")

        if not remote_file.is_file():
            raise IsADirectoryError(f"Remote path is not a file: {remote_path}")

        with open(remote_file, "r", encoding=encoding) as f:
            return f.read()

    def write_file_content(self, remote_path: str, content: str, encoding: str = "utf-8") -> None:
        """写入内容到远程文件

        Args:
            remote_path: 远程文件路径（本地环境中的路径）
            content: 文件内容
            encoding: 文件编码
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        remote_file = Path(remote_path)

        # 确保目录存在
        remote_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(remote_file, "w", encoding=encoding) as f:
            f.write(content)

    def path_exists(self, remote_path: str) -> bool:
        """检查远程路径是否存在

        Args:
            remote_path: 远程路径（本地环境中的路径）

        Returns:
            是否存在
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        return os.path.exists(remote_path)

    def is_file(self, remote_path: str) -> bool:
        """检查远程路径是否是文件

        Args:
            remote_path: 远程路径（本地环境中的路径）

        Returns:
            是否是文件
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        return os.path.isfile(remote_path)

    def is_directory(self, remote_path: str) -> bool:
        """检查远程路径是否是目录

        Args:
            remote_path: 远程路径（本地环境中的路径）

        Returns:
            是否是目录
        """
        if not self._is_ready:
            raise RuntimeError("Environment not ready")

        return os.path.isdir(remote_path)
