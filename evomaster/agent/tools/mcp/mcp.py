"""MCP 工具集成

将 MCP (Model Context Protocol) 服务器的工具包装为 EvoMaster 工具。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from ..base import BaseTool, ToolError

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession
    from evomaster.utils.types import ToolSpec


class MCPTool(BaseTool):
    """MCP 工具包装器

    将单个 MCP 工具包装为 EvoMaster BaseTool。

    特点：
    - 动态工具：运行时从 MCP 服务器获取
    - 异步转同步：MCP 是异步的，需要转换
    - Schema 转换：MCP schema -> ToolSpec
    - 元数据标记：标记工具来源（MCP 服务器）

    使用示例：
        mcp_tool = MCPTool(
            mcp_connection=connection,
            tool_name="github_create_issue",
            tool_description="Create a new GitHub issue",
            input_schema={...}
        )
        observation, info = mcp_tool.execute(session, args_json)
    """

    # 类属性（BaseTool 需要）
    name: ClassVar[str] = "mcp_tool"  # 会被实例属性覆盖
    params_class: ClassVar[type] = None  # MCP 工具不使用 params_class

    def __init__(
        self,
        mcp_connection,  # MCPConnection 实例
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        remote_tool_name: str | None = None,
    ):
        """初始化 MCP 工具

        Args:
            mcp_connection: MCP 连接实例
            tool_name: 工具名称（已添加服务器前缀）
            tool_description: 工具描述
            input_schema: 输入参数 schema（JSON Schema 格式）
        """
        super().__init__()

        # MCP 相关属性
        self.mcp_connection = mcp_connection
        self._tool_name = tool_name
        self._tool_description = tool_description
        self._input_schema = input_schema
        self._remote_tool_name = remote_tool_name
        # ✅ MCP 专用 event loop（由 MCPToolManager 或 Playground 注入）
        self._mcp_loop = None

        # 覆盖类属性
        self.name = tool_name

        # 元数据标记（由 MCPToolManager 设置）
        self._is_mcp_tool = True
        self._mcp_server = None  # 服务器名称

        # 统计信息
        self._call_count = 0
        self._last_error = None

    def execute(
        self,
        session: BaseSession,
        args_json: str
    ) -> tuple[str, dict[str, Any]]:
        """执行 MCP 工具

        Args:
            session: Session 实例（MCP 工具不使用，但保持接口一致）
            args_json: JSON 格式的参数

        Returns:
            (observation, info) 元组
            - observation: 返回给 Agent 的观察结果
            - info: 额外信息（包含 MCP 元数据）
        """
        try:
            # 1. 解析参数
            args = json.loads(args_json)
            self.logger.debug(f"Executing MCP tool {self._tool_name} with args: {args}")

            # 2. Apply path adaptor (if configured via playground hook)
            # Transforms arguments before sending to MCP tool (e.g., path conversion, credential injection)
            path_adaptor = getattr(self, "_path_adaptor", None)
            if path_adaptor is not None:
                workspace_path = (
                    getattr(getattr(session, "config", None), "workspace_path", None)
                    if session
                    else None
                ) or ""
                args = path_adaptor.resolve_args(
                    workspace_path,
                    args,
                    self._tool_name,
                    self._mcp_server or "",
                    input_schema=getattr(self, "_input_schema", None),
                )

            # 3. 调用 MCP 工具（异步转同步）
            result = self._call_mcp_tool_sync(args)

            # 4. 格式化输出
            observation = self._format_mcp_result(result)

            # 5. 更新统计
            self._call_count += 1
            self._last_error = None

            info = {
                "mcp_tool": self._tool_name,
                "mcp_server": self._mcp_server,
                "success": True,
                "call_count": self._call_count,
            }

            return observation, info

        except json.JSONDecodeError as e:
            self._last_error = str(e)
            raise ToolError(f"Invalid JSON arguments: {str(e)}")
        except Exception as e:
            self._last_error = str(e)
            self.logger.error(f"MCP tool {self._tool_name} failed: {e}")
            raise ToolError(f"MCP tool execution failed: {str(e)}")

    def _call_mcp_tool_sync(self, args: dict) -> Any:
        """同步调用 MCP 工具（内部处理异步）

        ✅ 关键：禁止 asyncio.run() 产生临时 loop，必须把协程丢到“同一个长期 loop”里执行，
        否则会出现 anyio/mcp stream 卡死、ClosedResourceError、cancel scope 错位等问题。
        """
        # 1) 必须有一个被注入的 MCP loop
        loop = getattr(self, "_mcp_loop", None)
        if loop is None:
            raise ToolError(
                "MCP loop not injected into MCPTool. "
                "Please set mcp_tool._mcp_loop = <persistent_event_loop> when creating tools."
            )
        if loop.is_closed():
            raise ToolError("MCP loop is closed; cannot call MCP tool")

        coro = self.mcp_connection.call_tool(self._remote_tool_name, args)

        try:
            # 2) 如果这个 loop 当前没有在运行（最常见：同步 Agent 场景），直接 run_until_complete
            if not loop.is_running():
                return loop.run_until_complete(coro)

            # 3) 如果 loop 在运行（比如你把 loop 放到后台线程 run_forever），用线程安全提交
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result(timeout=60)

        except concurrent.futures.TimeoutError:
            raise ToolError("MCP tool call timed out after 60 seconds")
        except Exception as e:
            raise ToolError(f"Failed to call MCP tool: {str(e)}")

    def _format_mcp_result(self, result: Any) -> str:
        """格式化 MCP 工具返回结果

        MCP 返回的是 content 列表，需要提取文本内容。
        支持多种 content 类型：text, json, image 等。

        Args:
            result: MCP 工具返回的原始结果

        Returns:
            格式化后的字符串
        """
        if isinstance(result, list):
            # MCP 返回的是 content 列表
            parts = []
            for item in result:
                # 处理不同类型的 content
                if hasattr(item, 'text'):
                    # Pydantic 模型
                    parts.append(item.text)
                elif isinstance(item, dict):
                    if 'text' in item:
                        parts.append(item['text'])
                    elif 'type' in item and item['type'] == 'text':
                        parts.append(item.get('text', ''))
                    else:
                        # 其他类型的 content，转为 JSON
                        parts.append(json.dumps(item, indent=2))
                else:
                    parts.append(str(item))
            return "\n".join(parts) if parts else ""
        elif isinstance(result, str):
            return result
        elif result is None:
            return ""
        else:
            # 其他类型，转为 JSON
            return json.dumps(result, indent=2, default=str)

    def get_tool_spec(self) -> ToolSpec:
        """获取工具规格（用于 LLM function calling）

        将 MCP 的 schema 转换为 EvoMaster 的 ToolSpec。

        Returns:
            ToolSpec 实例
        """
        from evomaster.utils.types import FunctionSpec, ToolSpec

        return ToolSpec(
            type="function",
            function=FunctionSpec(
                name=self._tool_name,
                description=self._tool_description,
                parameters=self._input_schema,
                strict=None,
            )
        )

    def get_stats(self) -> dict[str, Any]:
        """获取工具统计信息

        Returns:
            统计信息字典
        """
        return {
            "tool_name": self._tool_name,
            "mcp_server": self._mcp_server,
            "call_count": self._call_count,
            "last_error": self._last_error,
        }
