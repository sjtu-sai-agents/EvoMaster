"""Mat Master Playground 实现

材料科学 / 计算材料方向的 EvoMaster agent，接入 Mat 的 MCP 工具
（Structure Generator、Science Navigator、Document Parser、DPA Calculator）。
使用 MatMasterAgent：支持 functions.finish 归一化、仅 task_completed==true 时结束。
mat_master 在此复写 _setup_mcp_tools，在初始化 MCP 前设置 tool_include_only（仅注册指定工具），
不修改基类 core/playground.py。
"""

import asyncio
import json
import logging
from pathlib import Path

from evomaster.core import BasePlayground, register_playground

from .agent import MatMasterAgent


@register_playground("mat_master")
class MatMasterPlayground(BasePlayground):
    """Mat Master Playground

    材料科学向的 playground，使用 Mat 的 MCP 服务（结构生成、科学导航、
    文档解析、DPA 计算），支持 LiteLLM 与 Azure 的 LLM 配置格式。
    使用 MatMasterAgent：异步任务未完成时不会因 partial 结束，需 task_completed=true 才结束。

    使用方式：
        python run.py --agent mat_master --task "材料相关任务"
    """

    def __init__(self, config_dir: Path = None, config_path: Path = None):
        """初始化 MatMasterPlayground

        Args:
            config_dir: 配置目录路径，默认为 configs/mat_master/
            config_path: 配置文件完整路径（如果提供，会覆盖 config_dir）
        """
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "mat_master"

        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)

    def _create_agent(
        self,
        name: str,
        agent_config: dict,
        enable_tools: bool = True,
        llm_config_dict: dict | None = None,
        skill_registry=None,
    ):
        """创建 Mat Master 专用 Agent（MatMasterAgent），其余与基类一致"""
        from evomaster.agent import AgentConfig
        from evomaster.agent.context import ContextConfig
        from evomaster.utils import LLMConfig, create_llm

        max_turns = agent_config.get("max_turns", 20)
        context_config_dict = agent_config.get("context", {})
        context_config = ContextConfig(**context_config_dict)
        agent_cfg = AgentConfig(max_turns=max_turns, context_config=context_config)
        output_config = self._get_output_config()

        if llm_config_dict is None:
            llm_config_dict = self._setup_llm_config()
        llm = create_llm(LLMConfig(**llm_config_dict), output_config=output_config)
        self.logger.debug(f"Created independent LLM instance for {name} agent")

        system_prompt_file = agent_config.get("system_prompt_file")
        user_prompt_file = agent_config.get("user_prompt_file")
        playground_base = Path(str(self.config_dir).replace("configs", "playground"))
        if system_prompt_file:
            prompt_path = Path(system_prompt_file)
            if not prompt_path.is_absolute():
                system_prompt_file = str((playground_base / prompt_path).resolve())
        if user_prompt_file:
            prompt_path = Path(user_prompt_file)
            if not prompt_path.is_absolute():
                user_prompt_file = str((playground_base / prompt_path).resolve())
        prompt_format_kwargs = agent_config.get("prompt_format_kwargs", {})

        agent = MatMasterAgent(
            llm=llm,
            session=self.session,
            tools=self.tools,
            system_prompt_file=system_prompt_file,
            user_prompt_file=user_prompt_file,
            prompt_format_kwargs=prompt_format_kwargs,
            config=agent_cfg,
            skill_registry=skill_registry,
            output_config=output_config,
            config_dir=self.config_dir,
            enable_tools=enable_tools,
        )
        agent.set_agent_name(name)
        return agent

    def _setup_mcp_tools(self):
        """初始化 MCP 工具（mat_master 复写：在添加服务器前设置 tool_include_only）。

        与基类逻辑一致，仅在步骤 7 与 8 之间从 config.mcp.tool_include_only 写入 manager，
        使 mat_sn 等仅注册指定工具（如 web-search、search-papers-enhanced）。
        """
        from evomaster.agent.tools import MCPToolManager

        mcp_config = getattr(self.config, "mcp", None)
        if not mcp_config or not isinstance(mcp_config, dict):
            if not mcp_config:
                self.logger.debug("MCP not configured, skipping")
            else:
                self.logger.error("Invalid MCP config format, expected dict")
            return None
        if not mcp_config.get("enabled", True):
            self.logger.info("MCP is disabled in config")
            return None

        config_file = mcp_config.get("config_file", "mcp_config.json")
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = self.config_manager.config_dir / config_path
        if not config_path.exists():
            self.logger.warning(f"MCP config file not found: {config_path}")
            return None

        self.logger.info(f"Loading MCP config from: {config_path}")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                mcp_servers_config = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load MCP config: {e}")
            return None

        PLACEHOLDER = "__EVOMASTER_WORKSPACES__"

        def _deep_replace(obj, old: str, new: str):
            if isinstance(obj, str):
                return obj.replace(old, new)
            if isinstance(obj, list):
                return [_deep_replace(x, old, new) for x in obj]
            if isinstance(obj, dict):
                return {k: _deep_replace(v, old, new) for k, v in obj.items()}
            return obj

        try:
            if self.run_dir is not None:
                ws_root = str((Path(self.run_dir) / "workspaces").resolve())
                mcp_servers_config = _deep_replace(mcp_servers_config, PLACEHOLDER, ws_root)
                self.logger.info(f"[MCP] Replaced {PLACEHOLDER} -> {ws_root}")
            else:
                self.logger.debug(f"[MCP] run_dir is None, skip placeholder replace: {PLACEHOLDER}")
        except Exception as e:
            self.logger.warning(f"[MCP] Failed to replace placeholder paths: {e}")

        servers = self._parse_mcp_servers(mcp_servers_config)
        if not servers:
            self.logger.warning("No valid MCP servers found in config")
            return None

        self.logger.info("Setting up MCP tools...")
        manager = MCPToolManager()
        if mcp_config.get("path_adaptor") == "calculation":
            from evomaster.adaptors.calculation import get_calculation_path_adaptor

            calc_servers = mcp_config.get("calculation_servers")
            if calc_servers:
                manager.path_adaptor_servers = set(calc_servers)
            else:
                manager.path_adaptor_servers = {s.get("name") for s in servers if s.get("name")}
            manager.path_adaptor_factory = lambda: get_calculation_path_adaptor(mcp_config)
            self.logger.info("Calculation path adaptor enabled for servers: %s", manager.path_adaptor_servers)

        # mat_master：仅在此处设置 tool_include_only，基类 core 不包含此逻辑
        include_only = mcp_config.get("tool_include_only")
        if include_only and isinstance(include_only, dict):
            manager.tool_include_only = {
                k: list(v) if isinstance(v, (list, tuple)) else []
                for k, v in include_only.items()
            }
            self.logger.info("MCP tool_include_only set for servers: %s", list(manager.tool_include_only.keys()))

        async def init_mcp_servers():
            for server_config in servers:
                try:
                    await manager.add_server(**server_config)
                except Exception as e:
                    self.logger.error(f"Failed to add MCP server {server_config.get('name')}: {e}")

        if self._mcp_loop is None or self._mcp_loop.is_closed():
            self._mcp_loop = asyncio.new_event_loop()
            self._mcp_thread = self._start_loop_in_thread()

        manager.loop = self._mcp_loop
        future = asyncio.run_coroutine_threadsafe(init_mcp_servers(), self._mcp_loop)
        future.result()

        manager.register_tools(self.tools)
        tool_count = len(manager.get_tool_names())
        server_count = len(manager.get_server_names())
        self.logger.info(f"MCP tools setup complete: {tool_count} tools from {server_count} servers")
        return manager
