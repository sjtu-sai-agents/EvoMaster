"""EvoMaster Agent 模块

Agent 是 EvoMaster 的智能体组件，包含：
- 类型定义（Message, Dialog, Trajectory）- 从 utils 导入
- 上下文管理（ContextManager）
- Agent 基类和实现
- Session（与 Env 交互的介质）
- Tools（工具系统）
"""

from evomaster.utils.types import (
    Message,
    MessageRole,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
    ToolCall,
    FunctionCall,
    ToolSpec,
    FunctionSpec,
    Dialog,
    StepRecord,
    Trajectory,
    TaskInstance,
)
from .context import ContextManager, ContextConfig, TruncationStrategy
from .agent import BaseAgent, Agent, AgentConfig

# Session 子模块
from .session import (
    BaseSession,
    SessionConfig,
    DockerSession,
    DockerSessionConfig,
)

# Tools 子模块
from .tools import (
    BaseTool,
    ToolRegistry,
    ToolError,
    create_default_registry,
    create_registry,
    BashTool,
    EditorTool,
    ThinkTool,
    FinishTool,
)

__all__ = [
    # Types
    "Message",
    "MessageRole",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "ToolCall",
    "FunctionCall",
    "ToolSpec",
    "FunctionSpec",
    "Dialog",
    "StepRecord",
    "Trajectory",
    "TaskInstance",
    # Context
    "ContextManager",
    "ContextConfig",
    "TruncationStrategy",
    # Agent
    "BaseAgent",
    "Agent",
    "AgentConfig",
    # Session
    "BaseSession",
    "SessionConfig",
    "DockerSession",
    "DockerSessionConfig",
    # Tools
    "BaseTool",
    "ToolRegistry",
    "ToolError",
    "create_default_registry",
    "create_registry",
    "BashTool",
    "EditorTool",
    "ThinkTool",
    "FinishTool",
]
