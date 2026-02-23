"""EvoMaster - 科学实验迭代 Agent 系统

EvoMaster 是一个用于迭代完成科学实验任务的 Agent 系统，
主要针对 MLE、Phys、Embody 等科学实验场景。

核心组件（三层架构）：
- agent: 智能体（包含 Session、Tools）
- env: 环境（集群调度、Docker 沙箱）
- skills: 技能
"""

__version__ = "0.1.0"

# 从 agent 模块导出常用类
from evomaster.agent import (
    # Agent
    BaseAgent,
    Agent,
    AgentConfig,
    # Types
    Dialog,
    Message,
    Trajectory,
    TaskInstance,
    # Session
    BaseSession,
    SessionConfig,
    DockerSession,
    DockerSessionConfig,
    # Tools
    BaseTool,
    ToolRegistry,
    create_default_registry,
)

# 从 utils 模块导出工具类和类型
from evomaster.utils import (
    # LLM
    BaseLLM,
    LLMConfig,
    LLMResponse,
    OpenAILLM,
    AnthropicLLM,
    create_llm,
    # Types
    MessageRole,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
    Message,
    FunctionCall,
    ToolCall,
    FunctionSpec,
    ToolSpec,
    Dialog,
    StepRecord,
    Trajectory,
    TaskInstance,
)

# 从 config 模块导出配置管理
from evomaster.config import (
    # 配置基类
    BaseConfig,
    # Env 配置
    EnvConfig,
    ClusterConfig,
    ClusterPoolConfig,
    DockerEnvConfig,
    SchedulerConfig,
    # 日志配置
    LoggingConfig,
    # 顶层配置
    EvoMasterConfig,
    # 配置管理器
    ConfigManager,
    get_config_manager,
    load_config,
    get_config,
)

__all__ = [
    # Agent
    "BaseAgent",
    "Agent",
    "AgentConfig",
    # Types (from utils)
    "MessageRole",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "Message",
    "FunctionCall",
    "ToolCall",
    "FunctionSpec",
    "ToolSpec",
    "Dialog",
    "StepRecord",
    "Trajectory",
    "TaskInstance",
    # Session
    "BaseSession",
    "SessionConfig",
    "DockerSession",
    "DockerSessionConfig",
    # Tools
    "BaseTool",
    "ToolRegistry",
    "create_default_registry",
    # Utils - LLM
    "BaseLLM",
    "LLMConfig",
    "LLMResponse",
    "OpenAILLM",
    "AnthropicLLM",
    "create_llm",
    # Config
    "BaseConfig",
    "EnvConfig",
    "ClusterConfig",
    "ClusterPoolConfig",
    "DockerEnvConfig",
    "SchedulerConfig",
    "LoggingConfig",
    "EvoMasterConfig",
    "ConfigManager",
    "get_config_manager",
    "load_config",
    "get_config",
]
