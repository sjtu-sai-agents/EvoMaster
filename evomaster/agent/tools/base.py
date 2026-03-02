"""EvoMaster Agent Tools 基类

提供工具的基础抽象和注册机制。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from evomaster.utils.types import FunctionSpec, ToolSpec
    from evomaster.agent.session import BaseSession
    from evomaster.skills import SkillRegistry


class ToolError(Exception):
    """工具执行错误"""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ToolParameterError(ToolError):
    """工具参数错误"""
    
    def __init__(self, param_name: str, value: Any, hint: str = ""):
        self.param_name = param_name
        self.value = value
        message = f"Invalid parameter `{param_name}`: {value}"
        if hint:
            message += f". {hint}"
        super().__init__(message)


def _remove_unused_schema_info(schema: dict, model: type[BaseModel]) -> None:
    """移除 schema 中不需要的信息，使其更简洁"""
    def _remove_recursive(schema: dict, keys: list[str]):
        for key in keys:
            schema.pop(key, None)
        for _, v in schema.items():
            if isinstance(v, dict):
                _remove_recursive(v, keys)

    _remove_recursive(schema, ["default", "title", "additionalProperties"])
    schema.pop("description", None)


class BaseToolParams(BaseModel):
    """工具参数基类
    
    所有工具参数类应继承此类，并定义：
    - name: ClassVar[str] - 工具名称（暴露给 LLM）
    - __doc__: 工具描述（作为 function description）
    """
    
    name: ClassVar[str]
    model_config = ConfigDict(
        json_schema_extra=_remove_unused_schema_info,
    )


class BaseTool(ABC):
    """工具基类
    
    每个工具需要：
    1. 定义参数类（继承 BaseToolParams）
    2. 实现 execute 方法
    """
    
    # 工具名称
    name: ClassVar[str]
    
    # 参数类
    params_class: ClassVar[type[BaseToolParams]]
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def execute(self, session: BaseSession, args_json: str) -> tuple[str, dict[str, Any]]:
        """执行工具
        
        Args:
            session: 环境会话
            args_json: 参数 JSON 字符串
            
        Returns:
            (observation, info) 元组
            - observation: 返回给 Agent 的观察结果
            - info: 额外信息
        """
        pass

    def parse_params(self, args_json: str) -> BaseToolParams:
        """解析参数
        
        Args:
            args_json: JSON 字符串格式的参数
            
        Returns:
            解析后的参数对象
        """
        return self.params_class.model_validate_json(args_json)

    def get_tool_spec(self) -> ToolSpec:
        """获取工具规格（用于 LLM function calling）"""
        from evomaster.utils.types import FunctionSpec, ToolSpec

        return ToolSpec(
            type="function",
            function=FunctionSpec(
                name=self.name,
                description=(self.params_class.__doc__ or "").strip().replace("\n    ", "\n"),
                parameters=self.params_class.model_json_schema(),
                strict=None,
            )
        )


class ToolRegistry:
    """工具注册中心
    
    管理所有可用工具，支持动态注册和获取。
    """
    
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def register(self, tool: BaseTool) -> None:
        """注册工具
        
        Args:
            tool: 工具实例
        """
        if tool.name in self._tools:
            self.logger.warning(f"Tool {tool.name} already registered, overwriting")
        self._tools[tool.name] = tool
        self.logger.debug(f"Registered tool: {tool.name}")

    def register_many(self, tools: list[BaseTool]) -> None:
        """批量注册工具"""
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        """取消注册工具"""
        if name in self._tools:
            del self._tools[name]
            self.logger.debug(f"Unregistered tool: {name}")

    def get_tool(self, name: str) -> BaseTool | None:
        """获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，不存在则返回 None
        """
        return self._tools.get(name)

    def get_all_tools(self) -> list[BaseTool]:
        """获取所有已注册的工具"""
        return list(self._tools.values())

    def get_tool_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    def get_tool_specs(self) -> list[ToolSpec]:
        """获取所有工具的规格列表（用于 LLM）"""
        return [tool.get_tool_spec() for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # MCP 工具相关方法（支持方案C：混合方案）

    def get_mcp_tools(self) -> list[BaseTool]:
        """获取所有 MCP 工具

        通过检查工具的 _is_mcp_tool 属性来识别 MCP 工具。

        Returns:
            MCP 工具列表
        """
        return [
            tool for tool in self._tools.values()
            if getattr(tool, '_is_mcp_tool', False)
        ]

    def get_builtin_tools(self) -> list[BaseTool]:
        """获取所有内置工具（非 MCP 工具）

        Returns:
            内置工具列表
        """
        return [
            tool for tool in self._tools.values()
            if not getattr(tool, '_is_mcp_tool', False)
        ]

    def get_tools_by_server(self, server_name: str) -> list[BaseTool]:
        """获取特定 MCP 服务器的所有工具

        Args:
            server_name: MCP 服务器名称

        Returns:
            该服务器的工具列表
        """
        return [
            tool for tool in self._tools.values()
            if getattr(tool, '_mcp_server', None) == server_name
        ]

    def get_mcp_server_names(self) -> list[str]:
        """获取所有 MCP 服务器名称

        Returns:
            服务器名称列表（去重）
        """
        servers = set()
        for tool in self._tools.values():
            server = getattr(tool, '_mcp_server', None)
            if server:
                servers.add(server)
        return sorted(list(servers))



def create_default_registry(skill_registry: SkillRegistry | None = None) -> ToolRegistry:
    """创建默认的工具注册中心，包含所有内置工具

    Args:
        skill_registry: 可选的 SkillRegistry 实例，如果提供则注册 SkillTool
    """
    return create_registry(builtin_names=["*"], skill_registry=skill_registry)


# 所有 builtin 工具名称 → 工厂函数映射
_BUILTIN_TOOL_FACTORIES: dict[str, Any] = None  # type: ignore[assignment]


def _get_builtin_factories() -> dict[str, Any]:
    """懒加载 builtin 工具的工厂映射（名称 → 无参构造函数）"""
    global _BUILTIN_TOOL_FACTORIES
    if _BUILTIN_TOOL_FACTORIES is None:
        from .builtin import BashTool, EditorTool, ThinkTool, FinishTool
        _BUILTIN_TOOL_FACTORIES = {
            "execute_bash": BashTool,
            "str_replace_editor": EditorTool,
            "think": ThinkTool,
            "finish": FinishTool,
        }
    return _BUILTIN_TOOL_FACTORIES


ALL_BUILTIN_TOOL_NAMES: list[str] | None = None  # populated lazily


def get_all_builtin_tool_names() -> list[str]:
    """返回所有 builtin 工具名称"""
    global ALL_BUILTIN_TOOL_NAMES
    if ALL_BUILTIN_TOOL_NAMES is None:
        ALL_BUILTIN_TOOL_NAMES = list(_get_builtin_factories().keys())
    return ALL_BUILTIN_TOOL_NAMES


def create_registry(
    builtin_names: list[str] | None = None,
    skill_registry: SkillRegistry | None = None,
) -> ToolRegistry:
    """创建工具注册中心，支持按名称筛选 builtin 工具

    Args:
        builtin_names: 需要注册的 builtin 工具名称列表。
            - None 或 ["*"] → 注册全部 builtin 工具
            - [] → 不注册任何 builtin（仅 skill / MCP）
            - ["execute_bash", "finish"] → 仅注册指定工具
        skill_registry: 可选的 SkillRegistry 实例，如果提供则注册 SkillTool
    """
    factories = _get_builtin_factories()

    registry = ToolRegistry()
    tools: list[BaseTool] = []

    # 确定需要实例化的 builtin 工具
    if builtin_names is None or builtin_names == ["*"]:
        # 全部
        tools.extend(factory() for factory in factories.values())
    else:
        for name in builtin_names:
            if name == "*":
                # 混入 "*" 时等价全部
                tools = [factory() for factory in factories.values()]
                break
            if name not in factories:
                raise ValueError(
                    f"Unknown builtin tool '{name}'. "
                    f"Available: {list(factories.keys())}"
                )
            tools.append(factories[name]())

    # 如果提供了 skill_registry，注册 SkillTool
    if skill_registry is not None:
        from .skill import SkillTool
        tools.append(SkillTool(skill_registry))

    registry.register_many(tools)
    return registry

