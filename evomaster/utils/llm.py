"""EvoMaster LLM 接口封装

提供统一的 LLM 调用接口，支持多种提供商。
"""

from __future__ import annotations

import logging
import sys
import time
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from evomaster.utils.types import AssistantMessage, Dialog, FunctionCall, ToolCall


def truncate_content(content: str, max_length: int = 5000, head_length: int = 2500, tail_length: int = 2500) -> str:
    """截断内容，如果超过最大长度，保留开头和结尾部分
    
    Args:
        content: 要截断的内容
        max_length: 最大长度阈值，超过此长度才截断
        head_length: 保留的开头部分长度
        tail_length: 保留的结尾部分长度
    
    Returns:
        截断后的内容
    """
    if len(content) <= max_length:
        return content
    return content[:head_length] + "\n... [truncated] ...\n" + content[-tail_length:]


class LLMConfig(BaseModel):
    """LLM 配置"""
    provider: Literal["openai", "anthropic","deepseek","openrouter"] = Field(description="LLM 提供商")
    model: str = Field(description="模型名称")
    api_key: str = Field(description="API Key，必须在配置中提供")
    base_url: str | None = Field(default=None, description="API Base URL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="采样温度")
    max_tokens: int | None = Field(default=None, description="最大生成 token 数")
    timeout: int = Field(default=300, description="请求超时时间（秒）")
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: float = Field(default=1.0, description="重试延迟（秒）")
    use_completion_api: bool = Field(default=False, description="使用 Completion API 而非 Chat API")


class LLMResponse(BaseModel):
    """LLM 响应"""
    content: str | None = Field(default=None, description="生成的文本内容")
    tool_calls: list[ToolCall] | None = Field(default=None, description="工具调用列表")
    finish_reason: str | None = Field(default=None, description="结束原因")
    usage: dict[str, int] = Field(default_factory=dict, description="Token 使用统计")
    meta: dict[str, Any] = Field(default_factory=dict, description="其他元数据")

    def to_assistant_message(self) -> AssistantMessage:
        """转换为 AssistantMessage"""
        return AssistantMessage(
            content=self.content,
            tool_calls=self.tool_calls,
            meta={
                "finish_reason": self.finish_reason,
                "usage": self.usage,
                **self.meta,
            }
        )


class BaseLLM(ABC):
    """LLM 基类

    定义统一的 LLM 调用接口。
    """

    def __init__(self, config: LLMConfig, output_config: dict[str, Any] | None = None):
        """初始化 LLM

        Args:
            config: LLM 配置
            output_config: 输出显示配置，包含：
                - show_in_console: 是否在终端显示
                - log_to_file: 是否记录到日志文件
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.output_config = output_config or {}
        self.show_in_console = self.output_config.get("show_in_console", False)
        self.log_to_file = self.output_config.get("log_to_file", False)
        # 跟踪已记录的消息数量，用于避免重复记录系统消息和初始任务描述
        self._logged_message_count = 0
        self._setup()

    def _setup(self) -> None:
        """初始化设置，由子类实现"""
        pass

    @abstractmethod
    def _call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 LLM API（子类实现）

        Args:
            messages: 消息列表（API 格式）
            tools: 工具规格列表（API 格式）
            **kwargs: 额外参数

        Returns:
            LLM 响应
        """
        pass

    def query(
        self,
        dialog: Dialog,
        **kwargs: Any,
    ) -> AssistantMessage:
        """查询 LLM

        Args:
            dialog: 对话对象
            **kwargs: 额外参数（覆盖配置）

        Returns:
            助手消息
        """
        # 转换为 API 格式
        messages = dialog.get_messages_for_api()
        tools = self._convert_tools(dialog.tools) if dialog.tools else None

        # 记录请求（如果启用日志）
        if self.log_to_file:
            self._log_request(messages, tools)

        # 调用 API（带重试）
        # breakpoint()
        response = self._call_with_retry(messages, tools, **kwargs)
        # breakpoint()
        # 记录响应（如果启用日志）
        if self.log_to_file:
            self._log_response(response)

        # 转换为 AssistantMessage
        return response.to_assistant_message()

    def _log_request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> None:
        """记录 LLM 请求到日志

        优化：只记录新增的消息，避免重复记录系统消息和初始任务描述。
        第一次请求时记录所有消息，后续请求只记录新增的消息。
        当检测到消息数量减少时（如重置context后），重置计数器并记录所有消息。
        """
        self.logger.info("=" * 80)
        self.logger.info("LLM Request:")
        self.logger.info(f"Model: {self.config.model}")
        if tools:
            self.logger.info(f"Tools: {[t.get('function', {}).get('name', 'unknown') for t in tools]}")
        
        # 检测是否是新对话开始（消息数量减少，通常发生在重置context后）
        if len(messages) <= self._logged_message_count:
            # 消息数量减少，说明是新对话开始，重置计数器
            self.logger.info("New conversation detected (message count decreased), resetting log counter")
            self._logged_message_count = 0
        
        # 计算需要记录的消息
        new_messages = messages[self._logged_message_count:]

        if self._logged_message_count == 0:
            # 第一次请求，记录所有消息（包括系统消息和初始任务描述）
            self.logger.info("Messages:")
            for i, msg in enumerate(messages):
                self._log_single_message(i + 1, msg)
            self._logged_message_count = len(messages)
        else:
            # 后续请求，只记录新增的消息
            if new_messages:
                self.logger.info(f"New Messages (continuing from message {self._logged_message_count + 1}):")
                for i, msg in enumerate(new_messages):
                    self._log_single_message(self._logged_message_count + i + 1, msg)
                self._logged_message_count = len(messages)
            else:
                # 没有新消息（可能由于上下文截断导致消息数量减少）
                self.logger.info(f"Messages: (same as previous, total: {len(messages)})")
                # 更新已记录的消息数量，避免后续重复
                self._logged_message_count = len(messages)

        self.logger.info("=" * 80)

    def _log_single_message(self, index: int, msg: dict[str, Any]) -> None:
        """记录单条消息，处理工具调用的特殊显示

        Args:
            index: 消息序号
            msg: 消息字典
        """
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        # 如果是 assistant 消息且有工具调用
        if role == "assistant" and tool_calls:
            if content:
                # 有文本内容，先显示内容
                content_display = truncate_content(content) if isinstance(content, str) else content
                self.logger.info(f"  [{index}] {role}: {content_display}")
            else:
                # 只有工具调用，显示占位符
                self.logger.info(f"  [{index}] {role}: [Calling {len(tool_calls)} tool(s)]")

            # 显示每个工具调用的详细信息
            for i, tc in enumerate(tool_calls):
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    tool_name = func.get("name", "unknown")
                    tool_args = func.get("arguments", "")

                    # 格式化参数（如果是 JSON 字符串，尝试解析并美化）
                    try:
                        import json
                        args_dict = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
                        args_display = json.dumps(args_dict, indent=2, ensure_ascii=False)
                        # 如果参数太长，截断
                        if len(args_display) > 500:
                            args_display = args_display[:500] + "\n    ... [truncated]"
                    except:
                        args_display = str(tool_args)

                    self.logger.info(f"      Tool #{i+1}: {tool_name}")
                    self.logger.info(f"      Args: {args_display}")
        else:
            # 正常消息（没有工具调用）
            if isinstance(content, str):
                content = truncate_content(content)
            self.logger.info(f"  [{index}] {role}: {content}")

    def _log_response(self, response: LLMResponse) -> None:
        """记录 LLM 响应到日志"""
        self.logger.info("=" * 80)
        self.logger.info("LLM Response:")
        if response.content:
            # 截断过长的内容
            content = truncate_content(response.content)
            self.logger.info(f"Content: {content}")
        if response.tool_calls:
            self.logger.info(f"Tool Calls: {[tc.function.name for tc in response.tool_calls]}")
        if response.usage:
            self.logger.info(f"Usage: {response.usage}")
        self.logger.info("=" * 80)

    def _call_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """带重试的调用

        Args:
            messages: 消息列表
            tools: 工具列表
            **kwargs: 额外参数

        Returns:
            LLM 响应
        """
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                return self._call(messages, tools, **kwargs)
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{self.config.max_retries}): {e}"
                )

                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)  # 指数退避
                    time.sleep(delay)

        # 所有重试失败
        raise RuntimeError(f"LLM call failed after {self.config.max_retries} attempts") from last_error

    def _convert_tools(self, tool_specs: list) -> list[dict[str, Any]]:
        """转换工具规格为 API 格式

        Args:
            tool_specs: ToolSpec 列表

        Returns:
            API 格式的工具列表
        """
        return [spec.model_dump() for spec in tool_specs]


class OpenAILLM(BaseLLM):
    """OpenAI LLM 实现

    支持 OpenAI API 和兼容接口（如 vLLM, Ollama 等）。
    """

    def _setup(self) -> None:
        """设置 OpenAI 客户端"""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )

        # API key 必须在配置中提供
        if not self.config.api_key:
            raise ValueError("OpenAI API key must be provided in config")

        # 创建客户端
        client_kwargs = {"api_key": self.config.api_key}
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url

        self.client = OpenAI(**client_kwargs)

    def _call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 OpenAI API"""
        # 构建请求参数
        request_params = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "timeout": kwargs.get("timeout", self.config.timeout)
        }

        if self.config.max_tokens:
            request_params["max_tokens"] = kwargs.get("max_tokens", self.config.max_tokens)

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # 调用 API
        response = self.client.chat.completions.create(**request_params)

        # 解析响应
        choice = response.choices[0]
        message = choice.message

        # 提取工具调用
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    type="function",
                    function=FunctionCall(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            meta={
                "model": response.model,
                "response_id": response.id,
            }
        )

class DeepSeekLLM(BaseLLM):
    """DeepSeek LLM 实现

    支持 Chat Completion API 和 Completion API。
    """

    def _setup(self) -> None:
        """设置 OpenAI 客户端"""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )

        # API key 必须在配置中提供
        if not self.config.api_key:
            raise ValueError("OpenAI API key must be provided in config")

        # 创建客户端
        client_kwargs = {"api_key": self.config.api_key}
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url

        self.client = OpenAI(**client_kwargs)

    def _messages_to_prompt(self, messages: list[dict[str, Any]]) -> str:
        """将消息列表转换为单个 prompt 字符串（用于 Completion API）

        格式与 X-Master 的 r1_tool.jinja 模板一致
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                parts.append(content)
            elif role == "user":
                parts.append(f"<｜User｜> {content} <｜Assistant｜>")
            elif role == "assistant":
                parts.append(content)
            elif role == "tool":
                # 工具结果包装在 execution_results 标签中
                parts.append(f"<execution_results>{content}</execution_results>")

        return "".join(parts)

    def _call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 DeepSeek API"""
        if self.config.use_completion_api:
            return self._call_completion(messages, **kwargs)
        else:
            return self._call_chat(messages, tools, **kwargs)

    def _call_completion(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 Completion API"""
        prompt = self._messages_to_prompt(messages)

        request_params = {
            "model": self.config.model,
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "timeout": kwargs.get("timeout", self.config.timeout),
        }

        if self.config.max_tokens:
            request_params["max_tokens"] = kwargs.get("max_tokens", self.config.max_tokens)

        # 调用 Completion API
        response = self.client.completions.create(**request_params)

        # 解析响应
        choice = response.choices[0]

        return LLMResponse(
            content=choice.text,
            tool_calls=None,  # Completion API 不支持原生 tool calls
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            meta={
                "model": response.model,
                "response_id": response.id,
                "api_type": "completion",
            }
        )

    def _call_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 Chat Completion API"""
        # 构建请求参数
        request_params = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "timeout": kwargs.get("timeout", self.config.timeout),
            "extra_body": {
                "chat_template_kwargs": {"thinking": True},
                "separate_reasoning": True
            }
        }

        if self.config.max_tokens:
            request_params["max_tokens"] = kwargs.get("max_tokens", self.config.max_tokens)

        if tools:
            # 清理 tools 中的 None 值（如 strict=None），某些 API 不接受 None
            cleaned_tools = []
            for tool in tools:
                cleaned_tool = tool.copy()
                if "function" in cleaned_tool and isinstance(cleaned_tool["function"], dict):
                    cleaned_function = cleaned_tool["function"].copy()
                    # 移除 strict=None 字段
                    if cleaned_function.get("strict") is None:
                        cleaned_function.pop("strict", None)
                    cleaned_tool["function"] = cleaned_function
                cleaned_tools.append(cleaned_tool)
            request_params["tools"] = cleaned_tools
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # 调用 API
        response = self.client.chat.completions.create(**request_params)

        # 解析响应
        choice = response.choices[0]
        message = choice.message

        # 提取工具调用
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    type="function",
                    function=FunctionCall(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            meta={
                "model": response.model,
                "response_id": response.id,
                "api_type": "chat",
            }
        )


class AnthropicLLM(BaseLLM):
    """Anthropic LLM 实现

    支持 Claude 系列模型。
    """

    def _setup(self) -> None:
        """设置 Anthropic 客户端"""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "Anthropic package not installed. Install with: pip install anthropic"
            )

        # API key 必须在配置中提供
        if not self.config.api_key:
            raise ValueError("Anthropic API key must be provided in config")

        # 创建客户端
        client_kwargs = {"api_key": self.config.api_key}
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url

        self.client = Anthropic(**client_kwargs)

    def _call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用 Anthropic API"""
        # Anthropic 需要分离 system message
        system_message = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        # 构建请求参数
        request_params = {
            "model": self.config.model,
            "messages": user_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens or 4096),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "timeout": kwargs.get("timeout", self.config.timeout),
        }

        if system_message:
            request_params["system"] = system_message

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = kwargs.get("tool_choice", {"type": "auto"})

        # 调用 API
        response = self.client.messages.create(**request_params)

        # 解析响应
        content_text = None
        tool_calls = None

        for content in response.content:
            if content.type == "text":
                content_text = content.text
            elif content.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                # Anthropic 的工具调用格式需要转换
                import json
                tool_calls.append(
                    ToolCall(
                        id=content.id,
                        type="function",
                        function=FunctionCall(
                            name=content.name,
                            arguments=json.dumps(content.input),
                        )
                    )
                )

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            meta={
                "model": response.model,
                "response_id": response.id,
            }
        )


def create_llm(config: LLMConfig, output_config: dict[str, Any] | None = None) -> BaseLLM:
    """LLM 工厂函数

    Args:
        config: LLM 配置
        output_config: 输出显示配置

    Returns:
        LLM 实例

    Raises:
        ValueError: 不支持的提供商
    """
    if config.provider == "openai" or config.provider == "openrouter":
        return OpenAILLM(config, output_config=output_config)
    elif config.provider == "anthropic":
        return AnthropicLLM(config, output_config=output_config)
    elif config.provider == "deepseek":
        return DeepSeekLLM(config, output_config=output_config)
    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")
