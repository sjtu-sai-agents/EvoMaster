"""EvoMaster Utils 模块

工具类和辅助函数，包括：
- LLM 接口封装
- 基础类型定义
- 其他通用工具
"""

from .llm import (
    BaseLLM,
    LLMConfig,
    LLMResponse,
    OpenAILLM,
    AnthropicLLM,
    create_llm,
    build_multimodal_content,
    encode_image_to_base64,
    get_image_media_type,
)

from .types import (
    # Message 类型
    MessageRole,
    BaseMessage,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
    Message,
    # Function/Tool 定义
    FunctionCall,
    ToolCall,
    FunctionSpec,
    ToolSpec,
    # Dialog 和 Trajectory
    Dialog,
    StepRecord,
    Trajectory,
    TaskInstance,
)

__all__ = [
    # LLM
    "BaseLLM",
    "LLMConfig",
    "LLMResponse",
    "OpenAILLM",
    "AnthropicLLM",
    "create_llm",
    "build_multimodal_content",
    "encode_image_to_base64",
    "get_image_media_type",
    # Types
    "MessageRole",
    "BaseMessage",
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
]
