"""EvoMaster Agent 类型定义

定义 Agent 系统中使用的核心数据类型，包括消息、对话、轨迹等。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FunctionCall(BaseModel):
    """函数调用定义"""
    name: str = Field(description="函数名称")
    arguments: str = Field(description="函数参数，JSON 字符串格式")


class ToolCall(BaseModel):
    """工具调用定义"""
    id: str = Field(description="工具调用的唯一标识符")
    type: Literal["function"] = "function"
    function: FunctionCall = Field(description="函数调用详情")


class BaseMessage(BaseModel):
    """消息基类"""
    role: MessageRole = Field(description="消息角色")
    content: str | None = Field(default=None, description="消息内容")
    meta: dict[str, Any] = Field(default_factory=dict, description="元数据")


class SystemMessage(BaseMessage):
    """系统消息"""
    role: MessageRole = MessageRole.SYSTEM


class UserMessage(BaseMessage):
    """用户消息"""
    role: MessageRole = MessageRole.USER


class AssistantMessage(BaseMessage):
    """助手消息"""
    role: MessageRole = MessageRole.ASSISTANT
    tool_calls: list[ToolCall] | None = Field(default=None, description="工具调用列表")


class ToolMessage(BaseMessage):
    """工具响应消息"""
    role: MessageRole = MessageRole.TOOL
    tool_call_id: str = Field(description="对应的工具调用 ID")
    name: str = Field(description="工具名称")


# 消息联合类型
Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage


class ToolSpec(BaseModel):
    """工具规格定义，用于 LLM 的 function calling"""
    type: Literal["function"] = "function"
    function: FunctionSpec = Field(description="函数规格")


class FunctionSpec(BaseModel):
    """函数规格定义"""
    name: str = Field(description="函数名称")
    description: str = Field(description="函数描述")
    parameters: dict[str, Any] = Field(description="参数 JSON Schema")
    strict: bool | None = Field(default=None, description="是否严格模式")


class Dialog(BaseModel):
    """对话定义，包含消息列表和可用工具"""
    messages: list[Message] = Field(default_factory=list, description="消息列表")
    tools: list[ToolSpec] = Field(default_factory=list, description="可用工具列表")
    meta: dict[str, Any] = Field(default_factory=dict, description="元数据")

    def add_message(self, message: Message) -> None:
        """添加消息到对话"""
        self.messages.append(message)

    def get_messages_for_api(self) -> list[dict[str, Any]]:
        """获取用于 API 调用的消息格式"""
        result = []
        for msg in self.messages:
            msg_dict: dict[str, Any] = {"role": msg.role.value}
            content = msg.content

            # 部分 API（如 Claude/OpenRouter）要求 text content blocks 非空
            if isinstance(msg, AssistantMessage) and msg.tool_calls:
                if content is None or (isinstance(content, str) and not content.strip()):
                    content = " "
            elif isinstance(msg, ToolMessage):
                if content is None or (isinstance(content, str) and not content.strip()):
                    content = " "

            if content is not None:
                msg_dict["content"] = content
            if isinstance(msg, AssistantMessage) and msg.tool_calls:
                msg_dict["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            if isinstance(msg, ToolMessage):
                msg_dict["tool_call_id"] = msg.tool_call_id
                msg_dict["name"] = msg.name
            result.append(msg_dict)
        return result


class StepRecord(BaseModel):
    """单步执行记录"""
    step_id: int = Field(description="步骤编号")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    assistant_message: AssistantMessage | None = Field(default=None, description="助手消息")
    tool_responses: list[ToolMessage] = Field(default_factory=list, description="工具响应列表")
    meta: dict[str, Any] = Field(default_factory=dict, description="元数据")


class Trajectory(BaseModel):
    """任务执行轨迹，记录完整的执行过程"""
    task_id: str = Field(description="任务 ID")
    dialogs: list[Dialog] = Field(default_factory=list, description="对话列表")
    steps: list[StepRecord] = Field(default_factory=list, description="步骤记录")
    start_time: datetime = Field(default_factory=datetime.now, description="开始时间")
    end_time: datetime | None = Field(default=None, description="结束时间")
    status: Literal["running", "completed", "failed", "cancelled"] = Field(
        default="running", description="执行状态"
    )
    result: dict[str, Any] = Field(default_factory=dict, description="执行结果")
    meta: dict[str, Any] = Field(default_factory=dict, description="元数据")

    def add_step(self, step: StepRecord) -> None:
        """添加执行步骤"""
        self.steps.append(step)

    def finish(self, status: Literal["completed", "failed", "cancelled"], result: dict[str, Any] | None = None) -> None:
        """完成轨迹记录"""
        self.end_time = datetime.now()
        self.status = status
        if result:
            self.result = result


class TaskInstance(BaseModel):
    """任务实例定义"""
    task_id: str = Field(description="任务唯一标识")
    task_type: str = Field(default="general", description="任务类型")
    description: str = Field(default="", description="任务描述")
    input_data: dict[str, Any] = Field(default_factory=dict, description="输入数据")
    meta: dict[str, Any] = Field(default_factory=dict, description="元数据")

