"""EvoMaster Env 模块

Env 是 EvoMaster 的环境组件，负责：
- 可执行沙盒（Docker）
- 集群调度（k8s、ray、skypilot）
- 资源管理
- Bohrium 鉴权（MCP calculation storage/executor，见 .bohrium）
"""

from .base import BaseEnv, EnvConfig
from .local import LocalEnv, LocalEnvConfig
from .docker import DockerEnv, DockerEnvConfig
from .bohrium import (
    get_bohrium_credentials,
    get_bohrium_storage_config,
    inject_bohrium_executor,
)

# 解决 Pydantic 循环依赖问题：重建 EnvConfig 模型
# 确保 SessionConfig 子类已完全定义
def _rebuild_env_configs():
    """延迟重建 EnvConfig 模型以解决循环依赖"""
    try:
        # 确保 SessionConfig 子类已导入
        from evomaster.agent.session import DockerSessionConfig, LocalSessionConfig
        # 重建 EnvConfig 模型
        DockerEnvConfig.model_rebuild()
        LocalEnvConfig.model_rebuild()
    except Exception:
        # 如果重建失败，忽略（可能已经重建过或还未导入）
        pass

# 延迟执行重建，确保所有模块都已加载
_rebuild_env_configs()

__all__ = [
    "BaseEnv",
    "EnvConfig",
    "LocalEnv",
    "LocalEnvConfig",
    "DockerEnv",
    "DockerEnvConfig",
    "get_bohrium_credentials",
    "get_bohrium_storage_config",
    "inject_bohrium_executor",
]

