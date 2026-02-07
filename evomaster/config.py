"""EvoMaster 配置管理

提供统一的配置加载和管理功能，所有配置类都继承自 BaseConfig。
支持从 .env 加载环境变量，并在配置中将 ${VAR} 替换为 os.environ 中的值。
"""

from __future__ import annotations

import os
import re
from abc import ABC
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

# 匹配 ${VAR_NAME}，VAR_NAME 为字母、数字、下划线
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def _substitute_env(value: Any) -> Any:
    """递归将配置中的 ${VAR} 替换为 os.environ.get(\"VAR\", \"\")。"""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""),
            value,
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(item) for item in value]
    return value


# ============================================
# 基础配置类
# ============================================

class BaseConfig(BaseModel, ABC):
    """配置基类

    所有配置类都应继承此类，使用 Pydantic 进行验证。
    """

    class Config:
        extra = "allow"  # 允许额外字段
        arbitrary_types_allowed = True


# ============================================
# Env 配置
# ============================================

class ClusterPoolConfig(BaseConfig):
    """集群资源池配置"""
    type: str = Field(description="资源类型: cpu, gpu")
    max_concurrent: int = Field(default=5, description="最大并发数")
    resource_limits: dict[str, Any] = Field(default_factory=dict, description="资源限制")


class ClusterConfig(BaseConfig):
    """集群配置"""
    debug_pool: ClusterPoolConfig = Field(description="Debug 池配置")
    train_pool: ClusterPoolConfig = Field(description="训练池配置")


class DockerEnvConfig(BaseConfig):
    """Docker 环境配置"""
    base_image: str = Field(default="evomaster/base:latest", description="基础镜像")
    registry: str = Field(default="docker.io", description="镜像仓库")
    pull_policy: str = Field(default="if_not_present", description="拉取策略")


class SchedulerConfig(BaseConfig):
    """调度器配置"""
    type: str = Field(default="local", description="调度器类型: local, slurm, kubernetes")
    queue_timeout: int = Field(default=3600, description="队列超时时间（秒）")
    retry_failed: bool = Field(default=True, description="是否重试失败任务")
    max_retries: int = Field(default=3, description="最大重试次数")


class EnvConfig(BaseConfig):
    """环境配置（集群 / Docker / 调度器）。
    Bohrium 鉴权（BOHRIUM_ACCESS_KEY, BOHRIUM_PROJECT_ID 等）由 .env 提供，供 MCP calculation path adaptor 注入到 executor/storage。"""
    cluster: ClusterConfig = Field(description="集群配置")
    docker: DockerEnvConfig = Field(description="Docker 配置")
    scheduler: SchedulerConfig = Field(description="调度器配置")


# ============================================
# Skill 配置
# ============================================

class KnowledgeSkillConfig(BaseConfig):
    """Knowledge Skill 配置"""
    retrieval: dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "embedding_model": "text-embedding-ada-002",
            "top_k": 5,
            "similarity_threshold": 0.7,
        },
        description="检索配置"
    )


class OperatorSkillConfig(BaseConfig):
    """Operator Skill 配置"""
    load_meta_info: bool = Field(default=True, description="是否加载 meta_info")
    lazy_load_full_info: bool = Field(default=True, description="是否延迟加载 full_info")


class SkillConfig(BaseConfig):
    """Skill 配置"""
    skill_dir: str = Field(default="./evomaster/skills", description="Skill 目录")
    knowledge: KnowledgeSkillConfig = Field(default_factory=KnowledgeSkillConfig)
    operator: OperatorSkillConfig = Field(default_factory=OperatorSkillConfig)


# ============================================
# 日志配置
# ============================================

class LoggingConfig(BaseConfig):
    """日志配置"""
    level: str = Field(default="INFO", description="日志级别")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    file: str | None = Field(default=None, description="日志文件路径")
    console: bool = Field(default=True, description="是否输出到控制台")
    log_path: str | None = Field(default=None, description="日志文件保存路径（程序运行完成后保存）")


# ============================================
# 顶层配置
# ============================================

class EvoMasterConfig(BaseConfig):
    """EvoMaster 顶层配置

    包含所有子模块的配置。
    """

    # LLM 配置（存储为字典，按需转换为 LLMConfig）
    llm: dict[str, Any] = Field(default_factory=dict, description="LLM 配置")

    # Agent 配置（存储为字典，按需转换为 AgentConfig）
    agent: dict[str, Any] = Field(default_factory=dict, description="Agent 配置")

    # Session 配置（存储为字典，按需转换为 SessionConfig）
    session: dict[str, Any] = Field(default_factory=dict, description="Session 配置")

    # Env 配置
    env: EnvConfig = Field(default_factory=EnvConfig, description="环境配置")

    # Skill 配置
    skill: SkillConfig = Field(default_factory=SkillConfig, description="Skill 配置")

    # Skills 加载（Playground 用：enabled=true 时加载 SkillRegistry，skills_root 为技能目录）
    skills: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": False, "skills_root": "evomaster/skills"},
        description="Skills 启用与根目录",
    )

    # 日志配置
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="日志配置")

    # LLM 输出显示配置
    llm_output: dict[str, Any] = Field(
        default_factory=lambda: {
            "show_in_console": False,
            "log_to_file": False,
        },
        description="LLM 输出显示配置"
    )

    # 其他配置
    project_root: str = Field(default=".", description="项目根目录")
    workspace: str = Field(default="./workspace", description="工作目录")
    results_dir: str = Field(default="./results", description="结果保存目录")
    debug: bool = Field(default=False, description="是否启用调试模式")


# ============================================
# 配置管理器
# ============================================

class ConfigManager:
    """配置管理器

    从 YAML 文件加载配置并构造配置对象。
    """

    DEFAULT_CONFIG_FILE = "config.yaml"

    def __init__(self, config_dir: str | Path | None = None, config_file: str | None = None):
        """初始化配置管理器

        Args:
            config_dir: 配置文件目录，默认为项目根目录的 configs/
            config_file: 配置文件名，默认为 config.yaml
        """
        if config_dir is None:
            # 默认配置目录：项目根目录/configs
            project_root = Path(__file__).parent.parent
            config_dir = project_root / "configs"

        self.config_dir = Path(config_dir)
        self.config_file = config_file or self.DEFAULT_CONFIG_FILE
        self._config: EvoMasterConfig | None = None

    def load(self) -> EvoMasterConfig:
        """加载配置文件

        会尝试从项目根目录加载 .env，并将配置中的 ${VAR} 替换为环境变量值。
        Returns:
            EvoMaster 配置对象
        """
        if self._config is not None:
            return self._config

        if load_dotenv is not None:
            # 从 config_dir 向上查找 .env（如 configs/mat_master -> 项目根）
            for parent in [self.config_dir] + list(self.config_dir.parents):
                env_file = parent / ".env"
                if env_file.exists():
                    load_dotenv(env_file)
                    break
            else:
                load_dotenv()  # 回退到 cwd 及父目录

        config_path = self.config_dir / self.config_file

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)

        config_dict = _substitute_env(config_dict)

        # 构造配置对象
        self._config = EvoMasterConfig(**config_dict)
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键（支持点分隔的嵌套键，如 "agent.max_turns"）
            default: 默认值

        Returns:
            配置值
        """
        config = self.load()

        # 支持嵌套键
        keys = key.split(".")
        value = config.model_dump()
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value

    def get_llm_config(self, name: str | None = None) -> dict[str, Any]:
        """获取 LLM 配置

        Args:
            name: LLM 配置名称，None 则使用默认配置

        Returns:
            LLM 配置字典
        """
        config = self.load()

        if name is None:
            name = config.llm.get("default", "openai")

        llm_config = config.llm.get(name)
        if llm_config is None:
            raise ValueError(f"LLM config '{name}' not found")

        return llm_config

    def get_agent_config(self) -> dict[str, Any]:
        """获取 Agent 配置

        Returns:
            Agent 配置字典
        """
        config = self.load()
        return config.agent

    def get_session_config(self, session_type: str = "docker") -> dict[str, Any]:
        """获取 Session 配置

        Args:
            session_type: Session 类型（docker, local）

        Returns:
            Session 配置字典
        """
        config = self.load()
        session_config = config.session.get(session_type)
        if session_config is None:
            raise ValueError(f"Session config '{session_type}' not found")
        return session_config

    def get_env_config(self) -> EnvConfig:
        """获取 Env 配置

        Returns:
            Env 配置对象
        """
        config = self.load()
        return config.env

    def get_skill_config(self) -> SkillConfig:
        """获取 Skill 配置

        Returns:
            Skill 配置对象
        """
        config = self.load()
        return config.skill

    def get_logging_config(self) -> LoggingConfig:
        """获取日志配置

        Returns:
            日志配置对象
        """
        config = self.load()
        return config.logging

    def create_llm_from_config(self, name: str | None = None):
        """从配置创建 LLM 实例

        Args:
            name: LLM 配置名称

        Returns:
            LLM 实例
        """
        from evomaster.utils import LLMConfig, create_llm

        config_dict = self.get_llm_config(name)
        llm_config = LLMConfig(**config_dict)
        return create_llm(llm_config)


# ============================================
# 全局配置管理器
# ============================================

_config_manager: ConfigManager | None = None


def get_config_manager(config_dir: str | Path | None = None) -> ConfigManager:
    """获取全局配置管理器

    Args:
        config_dir: 配置目录（首次调用时设置）

    Returns:
        配置管理器实例
    """
    global _config_manager

    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)

    return _config_manager


def load_config() -> EvoMasterConfig:
    """快捷函数：加载配置文件

    Returns:
        配置对象
    """
    return get_config_manager().load()


def get_config(key: str, default: Any = None) -> Any:
    """快捷函数：获取配置项

    Args:
        key: 配置键
        default: 默认值

    Returns:
        配置值
    """
    return get_config_manager().get(key, default)
