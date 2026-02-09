"""EvoMaster Playground 基类

定义工作流的通用执行逻辑。
"""
from __future__ import annotations

import threading
import asyncio
import logging
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

from evomaster.config import ConfigManager
from evomaster.utils import LLMConfig, create_llm
from evomaster.agent import create_default_registry
from evomaster.agent.session import LocalSession, LocalSessionConfig, DockerSession, DockerSessionConfig
from evomaster.agent.tools import MCPToolManager
from evomaster.skills import SkillRegistry

from .exp import BaseExp


class BasePlayground:
    """Playground 基类

    定义工作流的通用生命周期管理：
    1. 加载配置
    2. 初始化所有组件
    3. 创建并运行实验
    4. 清理资源

    具体 playground 可以：
    - 继承此类
    - 覆盖 _create_exp() 以使用自定义 Exp 类
    - 覆盖 setup() 以添加额外初始化逻辑
    """

    def __init__(self, config_dir: str | Path | None = None, config_path: str | Path | None = None):
        """初始化 Playground

        Args:
            config_dir: 配置目录（默认为 configs/）
            config_path: 配置文件完整路径（如果提供，会覆盖 config_dir）
        """
        # 如果提供了 config_path，从中提取 config_dir 和 config_file
        if config_path is not None:
            config_path = Path(config_path)
            self.config_dir = config_path.parent
            config_file = config_path.name
        else:
            # 否则使用 config_dir 和默认的 config.yaml
            if config_dir is None:
                config_dir = Path(__file__).parent.parent.parent / "configs"
            self.config_dir = Path(config_dir)
            config_file = None  # 使用 ConfigManager 的默认值 config.yaml

        self.config_manager = ConfigManager(config_dir=self.config_dir, config_file=config_file)
        self.config = self.config_manager.load()
        self.config_path = self.config_dir / self.config_manager.config_file  # 保存实际使用的配置文件路径
        self.logger = logging.getLogger(self.__class__.__name__)
        self._mcp_loop = None
        self._mcp_thread = None


        # Run 目录管理
        self.run_dir = None
        self.log_file_handler = None

        # 组件存储
        self.session = None
        self.agent = None
        self.tools = None
    
    def _start_loop_in_thread(self) -> threading.Thread:

        def _runner():
            asyncio.set_event_loop(self._mcp_loop)
            self._mcp_loop.run_forever()

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        return t
    
    def set_run_dir(self, run_dir: str | Path, task_id: str | None = None) -> None:
        """设置 run 目录并创建目录结构

        创建以下目录结构：
        - run_dir/config.yaml (配置文件副本)
        - run_dir/logs/ (日志文件)
        - run_dir/trajectories/ (对话轨迹)
        - run_dir/workspace/ 或 run_dir/workspaces/{task_id}/ (工作空间)

        Args:
            run_dir: Run 目录路径
            task_id: 任务 ID（可选）。如果提供，workspace 会创建在 workspaces/{task_id} 下，
                    用于批量任务场景
        """
        self.run_dir = Path(run_dir)
        self.task_id = task_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        (self.run_dir / "logs").mkdir(exist_ok=True)
        (self.run_dir / "trajectories").mkdir(exist_ok=True)

        # 复制配置文件到 run_dir（只在第一个 task 时复制，避免并发冲突）
        config_copy = self.run_dir / "config.yaml"
        if self.config_path.exists() and not config_copy.exists():
            shutil.copy2(self.config_path, config_copy)
            self.logger.info(f"Copied config to: {config_copy}")

        # 创建 workspace 目录
        if task_id:
            # 批量任务模式：workspaces/{task_id}/
            (self.run_dir / "workspaces").mkdir(exist_ok=True)
            workspace_path = self.run_dir / "workspaces" / task_id
            workspace_path.mkdir(exist_ok=True)
        else:
            # 单任务模式：workspace/
            workspace_path = self.run_dir / "workspace"
            workspace_path.mkdir(exist_ok=True)

        # 动态更新配置中的 workspace_path
        self._update_workspace_path(workspace_path)

        # 设置日志文件到 run_dir/logs/
        self._setup_logging()

        self.logger.info(f"Run directory: {self.run_dir}")
        if task_id:
            self.logger.info(f"Task ID: {task_id}")
            self.logger.info(f"Workspace: {workspace_path}")

    def _update_workspace_path(self, workspace_path: Path) -> None:
        """动态更新配置中的 workspace_path

        在 Session 创建之前调用，确保 Session 使用 run_dir 下的 workspace。

        Args:
            workspace_path: 新的 workspace 路径（通常是 run_dir/workspace 或 run_dir/workspaces/{task_id}）
        """
        workspace_path_str = str(workspace_path.absolute())

        # 更新 session 配置中的 workspace_path 和 working_dir
        if hasattr(self.config, 'session'):
            session_config = self.config.session

            # 对于 dict 类型的配置
            if isinstance(session_config, dict):
                session_type = session_config.get('type', 'local')

                # 更新 Local Session
                if session_type == 'local' and 'local' in session_config:
                    session_config['local']['workspace_path'] = workspace_path_str
                    session_config['local']['working_dir'] = workspace_path_str
                    self.logger.debug(f"Updated local workspace path to: {workspace_path_str}")

                # 更新 Docker Session
                elif session_type == 'docker' and 'docker' in session_config:
                    docker_config = session_config['docker']
                    container_workspace = docker_config.get('working_dir', '/workspace')

                    # 更新 volumes 挂载
                    if 'volumes' not in docker_config:
                        docker_config['volumes'] = {}
                    docker_config['volumes'][workspace_path_str] = container_workspace

                    # 更新 workspace_path
                    docker_config['workspace_path'] = container_workspace
                    docker_config['working_dir'] = container_workspace

                    self.logger.debug(f"Updated Docker volume: {workspace_path_str} -> {container_workspace}")

            # 对于 Pydantic 模型（如果已加载）
            elif hasattr(session_config, 'local') and hasattr(session_config.local, 'workspace_path'):
                session_config.local.workspace_path = workspace_path_str
                session_config.local.working_dir = workspace_path_str
            elif hasattr(session_config, 'docker') and hasattr(session_config.docker, 'workspace_path'):
                session_config.docker.workspace_path = workspace_path_str
                session_config.docker.working_dir = workspace_path_str

        self.logger.info(f"Updated workspace path to: {workspace_path_str}")


    def _setup_logging(self) -> None:
        """设置日志文件路径

        优先级：
        1. 如果设置了 run_dir，则使用 run_dir/logs/{task_id}.log 或 run_dir/logs/evomaster.log
        2. 否则使用配置文件中的 log_path
        3. 如果都没有，则不记录到文件
        """
        # 移除旧的文件处理器（如果存在）
        if self.log_file_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.log_file_handler)
            self.log_file_handler.close()
            self.log_file_handler = None

        # 确定日志文件路径
        log_file = None
        if self.run_dir:
            # 优先使用 run_dir
            if hasattr(self, 'task_id') and self.task_id:
                # 批量任务模式：使用 task_id.log
                log_file = self.run_dir / "logs" / f"{self.task_id}.log"
            else:
                # 单任务模式：使用 evomaster.log
                log_file = self.run_dir / "logs" / "evomaster.log"
        else:
            # 使用配置文件中的路径
            log_path = getattr(self.config.logging, 'log_path', None)
            if log_path:
                log_file = Path(log_path)

        if log_file:
            # 确保日志目录存在
            log_file.parent.mkdir(parents=True, exist_ok=True)

            # 创建文件处理器（覆盖模式）
            self.log_file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
            self.log_file_handler.setLevel(getattr(logging, self.config.logging.level))
            self.log_file_handler.setFormatter(logging.Formatter(self.config.logging.format))

            # 添加到根logger
            root_logger = logging.getLogger()
            root_logger.addHandler(self.log_file_handler)

            self.log_path = str(log_file)
            self.logger.info(f"Logging to file: {log_file}")
        else:
            self.log_path = None

    def _setup_llm_config(self) -> dict:
        """准备 LLM 配置

        Returns:
            LLM 配置字典
        """
        llm_config_dict = self.config_manager.get_llm_config()
        return llm_config_dict

    def _setup_session(self) -> None:
        """创建并打开 Session（如果尚未创建）

        根据配置选择 local 或 docker session。
        """
        if self.session is None:
            session_type = self.config.session.get("type", "local")
            if session_type == "docker":
                session_config_dict = self.config.session.get("docker", {}).copy()
                # 同步 working_dir 和 workspace_path
                if "working_dir" in session_config_dict and "workspace_path" not in session_config_dict:
                    session_config_dict["workspace_path"] = session_config_dict["working_dir"]
                elif "workspace_path" in session_config_dict and "working_dir" not in session_config_dict:
                    session_config_dict["working_dir"] = session_config_dict["workspace_path"]
                elif "workspace_path" not in session_config_dict and "working_dir" not in session_config_dict:
                    session_config_dict["workspace_path"] = "/workspace"
                    session_config_dict["working_dir"] = "/workspace"
                session_config = DockerSessionConfig(**session_config_dict)
                self.session = DockerSession(session_config)
                self.logger.info(f"Using Docker session with image: {session_config.image}")
            else:
                session_config_dict = self.config.session.get("local", {}).copy()
                # 同步 working_dir 和 workspace_path
                if "working_dir" in session_config_dict and "workspace_path" not in session_config_dict:
                    session_config_dict["workspace_path"] = session_config_dict["working_dir"]
                elif "workspace_path" in session_config_dict and "working_dir" not in session_config_dict:
                    session_config_dict["working_dir"] = session_config_dict["workspace_path"]
                # 传递 config_dir 用于解析 symlinks 中的相对路径
                if "config_dir" not in session_config_dict:
                    session_config_dict["config_dir"] = str(self.config_dir)
                session_config = LocalSessionConfig(**session_config_dict)
                self.session = LocalSession(session_config)
                self.logger.info("Using Local session")
        
        # 打开 Session（如果尚未打开）
        if not self.session.is_open:
            self.session.open()
        else:
            self.logger.debug("Session already open, reusing existing session")

    def _setup_tools(self, skill_registry=None) -> None:
        """创建工具注册表并初始化 MCP 工具（如果配置了）
        
        Args:
            skill_registry: 可选的 SkillRegistry 实例，如果提供则注册 SkillTool
        """
        # 创建工具注册表（传入 skill_registry）
        self.tools = create_default_registry(skill_registry)

        # 初始化 MCP 工具（如果配置了）
        self.mcp_manager = None
        if hasattr(self.config, 'mcp') or hasattr(self.config, 'mcp_servers'):
            self.mcp_manager = self._setup_mcp_tools()

    def _get_output_config(self) -> dict:
        """获取 LLM 输出配置

        Returns:
            输出配置字典
        """
        llm_output_config = self.config.llm_output if hasattr(self.config, 'llm_output') else {}
        if isinstance(llm_output_config, dict):
            return llm_output_config
        else:
            return {}

    def _create_agent(
        self,
        name: str,
        agent_config: dict,
        enable_tools: bool = True,
        llm_config_dict: dict | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        """创建 Agent 实例

        每个 Agent 使用独立的 LLM 实例，确保日志记录独立。

        Args:
            name: Agent 名称
            agent_config: Agent 配置字典
            enable_tools: 是否启用工具调用
            llm_config_dict: LLM 配置字典（如果为 None，则从配置管理器获取）

        Returns:
            Agent 实例
        """
        from evomaster.agent import Agent, AgentConfig
        from evomaster.agent.context import ContextConfig
        from evomaster.utils import LLMConfig, create_llm

        # 提取 Agent 配置
        max_turns = agent_config.get('max_turns', 20)
        context_config_dict = agent_config.get('context', {})
        context_config = ContextConfig(**context_config_dict)
        agent_cfg = AgentConfig(max_turns=max_turns, context_config=context_config)

        # 获取输出配置
        output_config = self._get_output_config()

        # 为每个 Agent 创建独立的 LLM 实例
        if llm_config_dict is None:
            llm_config_dict = self._setup_llm_config()
        llm = create_llm(LLMConfig(**llm_config_dict), output_config=output_config)
        self.logger.debug(f"Created independent LLM instance for {name} agent")

        # 获取提示词文件路径
        system_prompt_file = agent_config.get('system_prompt_file')
        user_prompt_file = agent_config.get('user_prompt_file')


        playground_base = Path(str(self.config_dir).replace("configs", "playground"))
        # 解析 system_prompt_file
        if system_prompt_file:
            prompt_path = Path(system_prompt_file)
            if not prompt_path.is_absolute():
                # 修改：相对于 playground_base 解析
                system_prompt_file = str((playground_base / prompt_path).resolve())
        
        # 解析 user_prompt_file
        if user_prompt_file:
            prompt_path = Path(user_prompt_file)
            if not prompt_path.is_absolute():
                # 修改：相对于 playground_base 解析
                user_prompt_file = str((playground_base / prompt_path).resolve())

        # 获取提示词格式化参数（如果有）
        prompt_format_kwargs = agent_config.get('prompt_format_kwargs', {})

        # 创建 Agent
        # 注意：无论 enable_tools 是什么值，都传递 tools 给 Agent
        # enable_tools 只控制工具信息是否出现在提示词中，不影响工具注册
        agent = Agent(
            llm=llm,
            session=self.session,
            tools=self.tools,  # 始终传递 tools，工具始终注册
            system_prompt_file=system_prompt_file,
            user_prompt_file=user_prompt_file,
            prompt_format_kwargs=prompt_format_kwargs,
            config=agent_cfg,
            skill_registry=skill_registry,
            output_config=output_config,
            config_dir=self.config_dir,
            enable_tools=enable_tools,  # 控制工具信息是否出现在提示词中
        )
        
        # 设置Agent名称（用于轨迹文件中标识不同的agent）
        agent.set_agent_name(name)

        return agent

    def setup(self) -> None:
        """初始化所有组件

        支持单 agent 和多 agent 两种模式：
        - 如果配置中有 `agents:` 字段，则创建多个 agent（多 agent 模式）
        - 否则，如果配置中有 `agent:` 字段，则创建单个 agent（单 agent 模式，向后兼容）

        具体实现包括：
        1. 准备 LLM 配置
        2. 创建 Session（如果尚未创建）
        3. 加载 Skills（如果启用）
        3. 创建工具注册表并初始化 MCP 工具
        4. 创建 Agent(s)

        子类可以覆盖此方法添加额外逻辑。
        """
        self.logger.info("Setting up playground...")

        # 1. 准备 LLM 配置
        llm_config_dict = self._setup_llm_config()
        self._llm_config_dict = llm_config_dict  # 保存供子类使用

        # 2. 创建 Session（如果尚未创建）
        self._setup_session()

        # 3. 加载 Skills（如果启用）- 在多 agent 和单 agent 模式下都需要
        skill_registry = None
        config_dict = self.config.model_dump()
        skills_config = config_dict.get("skills", {})
        if skills_config.get("enabled", False):
            self.logger.info("Skills enabled, loading skill registry...")
            from pathlib import Path
            from evomaster.skills import SkillRegistry

            skills_root = Path(skills_config.get("skills_root", "evomaster/skills"))
            skill_registry = SkillRegistry(skills_root)
            self.logger.info(f"Loaded {len(skill_registry.get_all_skills())} skills")

        # 4. 创建工具注册表并初始化 MCP 工具（传入 skill_registry）
        self._setup_tools(skill_registry)

        # 5. 创建 Agent(s)
        agents_config = getattr(self.config, 'agents', None)
        if agents_config:
            # 多 agent 模式
            if not isinstance(agents_config, dict) or not agents_config:
                raise ValueError(
                    "Invalid 'agents' configuration. "
                    "Expected a non-empty dictionary with agent names as keys."
                )
            
            # 创建多个 agent
            for agent_name, agent_config in agents_config.items():
                enable_tools = agent_config.get('enable_tools', True)
                self.agent = self._create_agent(
                    name=agent_name,
                    agent_config=agent_config,
                    enable_tools=enable_tools,
                    llm_config_dict=llm_config_dict,
                    skill_registry=skill_registry,  # 传递 skill_registry
                )
                self.logger.info(f"{agent_name.capitalize()} Agent created")
            
            self.logger.info("Multi-agent playground setup complete")
        else:
            # 单 agent 模式（向后兼容）
            # skill_registry 已经在上面加载了，这里不需要重复加载

            agent_config_dict = getattr(self.config, 'agent', None)
            if not agent_config_dict:
                raise ValueError(
                    "No agent configuration found. "
                    "Please add either 'agent' or 'agents' section to config.yaml"
                )
            
            # 获取提示词文件路径（如果配置了）并添加到 agent_config_dict
            system_prompt_file = getattr(self.config, 'system_prompt_file', None)
            user_prompt_file = getattr(self.config, 'user_prompt_file', None)
            
            # 将提示词文件路径添加到 agent_config_dict（如果存在）
            if system_prompt_file:
                agent_config_dict = agent_config_dict.copy()
                agent_config_dict['system_prompt_file'] = system_prompt_file
            
            if user_prompt_file:
                if not isinstance(agent_config_dict, dict):
                    agent_config_dict = agent_config_dict.copy() if hasattr(agent_config_dict, 'copy') else dict(agent_config_dict)
                agent_config_dict['user_prompt_file'] = user_prompt_file
            
            # 创建单个 agent
            enable_tools = agent_config_dict.get('enable_tools', True)
            self.agent = self._create_agent(
                name="default",
                agent_config=agent_config_dict,
                enable_tools=enable_tools,
                llm_config_dict=llm_config_dict,
                skill_registry=skill_registry,
            )
            
            self.logger.info("Single-agent playground setup complete")

    def _setup_mcp_tools(self):
        """初始化 MCP 工具

        从 MCP 配置文件（JSON 格式）读取服务器列表，初始化连接并注册工具。

        Returns:
            MCPToolManager 实例，如果配置无效则返回 None
        """
        # 1. 检查 MCP 配置
        mcp_config = getattr(self.config, 'mcp', None)
        if not mcp_config:
            self.logger.debug("MCP not configured, skipping")
            return None

        # 2. 检查配置格式
        if not isinstance(mcp_config, dict):
            self.logger.error("Invalid MCP config format, expected dict")
            return None

        # 3. 检查是否启用
        if not mcp_config.get('enabled', True):
            self.logger.info("MCP is disabled in config")
            return None

        # 4. 获取配置文件路径
        config_file = mcp_config.get('config_file', 'mcp_config.json')

        # 5. 解析配置文件路径
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = self.config_manager.config_dir / config_path

        if not config_path.exists():
            self.logger.warning(f"MCP config file not found: {config_path}")
            return None

        # 5. 加载 MCP 配置
        self.logger.info(f"Loading MCP config from: {config_path}")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                mcp_servers_config = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load MCP config: {e}")
            return None
        
        # --- PATCH: replace placeholder paths in MCP config (global) ---
        PLACEHOLDER = "__EVOMASTER_WORKSPACES__"

        def _deep_replace(obj, old: str, new: str):
            """Recursively replace `old` -> `new` in any string inside dict/list structures."""
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
        
        # 6. 解析服务器配置
        servers = self._parse_mcp_servers(mcp_servers_config)
        if not servers:
            self.logger.warning("No valid MCP servers found in config")
            return None

        # 7. 初始化 MCP 管理器
        self.logger.info("Setting up MCP tools...")
        manager = MCPToolManager()

        # 子类可以复写此方法来注入自定义逻辑（如 path adaptor、tool_include_only）
        self._configure_mcp_manager(manager, mcp_config)

        # 8. 异步初始化 MCP 服务器
        async def init_mcp_servers():
            for server_config in servers:
                try:
                    await manager.add_server(**server_config)
                except Exception as e:
                    self.logger.error(f"Failed to add MCP server {server_config.get('name')}: {e}")

        # 创建并保存一个“长期存在”的 loop，专门给 MCP 用
        if self._mcp_loop is None or self._mcp_loop.is_closed():
            self._mcp_loop = asyncio.new_event_loop()
            self._mcp_thread = self._start_loop_in_thread()

        manager.loop = self._mcp_loop

        # ✅ 往 mcp_loop 提交协程
        future = asyncio.run_coroutine_threadsafe(init_mcp_servers(), self._mcp_loop)
        future.result()  # 阻塞等待初始化完成（同步代码里只能这么等）

        # 9. 注册 MCP 工具到主工具注册表
        manager.register_tools(self.tools)

        tool_count = len(manager.get_tool_names())
        server_count = len(manager.get_server_names())
        self.logger.info(f"MCP tools setup complete: {tool_count} tools from {server_count} servers")

        return manager

    def _configure_mcp_manager(self, manager: MCPToolManager, mcp_config: Dict[str, Any]) -> None:
        """配置 MCP 管理器的钩子方法

        子类可以复写此方法来注入自定义逻辑，例如：
        - path adaptor（路径适配器）
        - tool_include_only（工具过滤）
        - 其他自定义配置

        Args:
            manager: MCP 工具管理器实例
            mcp_config: MCP 配置字典

        示例:
            class MyPlayground(BasePlayground):
                def _configure_mcp_manager(self, manager, mcp_config):
                    # 注入自定义 adaptor
                    manager.path_adaptor_factory = lambda: MyAdaptor()
        """
        # 基类默认不做任何事情
        # 子类可以复写来添加自定义逻辑
        pass

    def _parse_mcp_servers(self, mcp_config: dict) -> list[dict]:
        """解析 MCP 服务器配置

        支持标准 MCP 格式和扩展格式。

        Args:
            mcp_config: MCP 配置字典

        Returns:
            服务器配置列表
        """
        servers = []
        mcp_servers = mcp_config.get('mcpServers', {})

        for name, config in mcp_servers.items():
            if 'command' in config:
                # 标准格式（stdio）
                servers.append({
                    'name': name,
                    'transport': 'stdio',
                    'command': config['command'],
                    'args': config.get('args', []),
                    'env': config.get('env', {})
                })
            elif 'transport' in config:
                # 扩展格式（http/sse）
                transport = config['transport'].lower()
                if transport in ['http', 'sse', 'streamable_http', 'streamable-http']:
                    servers.append({
                        'name': name,
                        'transport': transport,
                        'url': config['url'],
                        'headers': config.get('headers', {})
                    })
                else:
                    self.logger.warning(f"Unsupported transport for server {name}: {transport}")
            else:
                self.logger.warning(f"Invalid config for server {name}: missing 'command' or 'transport'")

        return servers

    def _create_exp(self):
        """创建 Exp 实例

        子类可以覆盖此方法使用自定义 Exp 类。
        """
        exp = BaseExp(self.agent, self.config)
        # 传递 run_dir 给 Exp
        if self.run_dir:
            exp.set_run_dir(self.run_dir)
        return exp

    def _setup_trajectory_file(self, output_file: str | Path | None = None) -> Path | None:
        """设置轨迹文件路径

        确定轨迹文件路径并设置到 BaseAgent。优先级：
        1. 如果提供了 output_file，则使用该路径
        2. 如果设置了 run_dir，则自动保存到 trajectories/
           - 批量任务模式：trajectories/{task_id}/trajectory.json
           - 单任务模式：trajectories/trajectory.json

        Args:
            output_file: 结果保存文件路径（可选）

        Returns:
            轨迹文件路径，如果未设置则返回 None
        """
        trajectory_file = None
        if output_file:
            trajectory_file = Path(output_file)
        elif self.run_dir:
            # 如果设置了 run_dir，则自动保存到 trajectories/
            if hasattr(self, 'task_id') and self.task_id:
                # 批量任务模式：保存到 trajectories/{task_id}/trajectory.json
                trajectory_dir = self.run_dir / "trajectories" / self.task_id
                trajectory_dir.mkdir(parents=True, exist_ok=True)
                trajectory_file = trajectory_dir / "trajectory.json"
            else:
                # 单任务模式：保存到 trajectories/trajectory.json
                trajectory_file = self.run_dir / "trajectories" / "trajectory.json"
        
        # 设置轨迹文件路径到BaseAgent（所有agent共享同一个文件）
        if trajectory_file:
            from evomaster.agent import BaseAgent
            BaseAgent.set_trajectory_file_path(trajectory_file)
            self.logger.info(f"Trajectory file set to: {trajectory_file}")
        
        return trajectory_file

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        """运行工作流

        Args:
            task_description: 任务描述
            output_file: 结果保存文件（可选，如果设置了 run_dir 则自动保存到 trajectories/）

        Returns:
            运行结果
        """
        try:
            self.setup()

            # 设置轨迹文件路径
            self._setup_trajectory_file(output_file)

            # 创建并运行实验
            exp = self._create_exp()

            self.logger.info("Running experiment...")
            result = exp.run(task_description)

            return result

        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """清理资源

        对于 DockerSession，如果 auto_remove=False，则保留容器不关闭 session，
        以便在后续运行中复用同一个容器。
        """
        if self.mcp_manager:
            try:
                loop = self._mcp_loop
                t = self._mcp_thread

                if loop is not None and not loop.is_closed():
                    # 1) 先在 MCP loop 里执行异步 cleanup
                    fut = asyncio.run_coroutine_threadsafe(self.mcp_manager.cleanup(), loop)
                    fut.result()

                    # 2) 停 loop
                    if loop.is_running():
                        loop.call_soon_threadsafe(loop.stop)

                    # 3) 等线程退出 run_forever
                    if t is not None and t.is_alive():
                        t.join(timeout=5)

                    # 4) 确认 loop 不跑了再 close
                    if not loop.is_closed():
                        loop.close()

                self._mcp_loop = None
                self._mcp_thread = None

            except Exception as e:
                self.logger.warning(f"Error cleaning up MCP: {e}")


        # # 清理 MCP 连接
        # if self.mcp_manager:
        #     try:
        #         import asyncio
        #         asyncio.run(self.mcp_manager.cleanup())
        #         self.logger.debug("MCP connections cleaned up")
        #     except Exception as e:
        #         self.logger.warning(f"Error cleaning up MCP: {e}")

        if self.session:
            # 检查是否是 DockerSession 且配置了保留容器
            should_keep_session = False
            if isinstance(self.session, DockerSession):
                if not self.session.config.auto_remove:
                    should_keep_session = True
                    self.logger.info("Keeping Docker session and container for reuse (auto_remove=False)")
            
            if not should_keep_session:
                try:
                    self.session.close()
                    self.logger.debug("Session closed")
                except Exception as e:
                    self.logger.warning(f"Error closing session: {e}")
            else:
                # 只标记关闭状态，但不实际关闭 session（容器继续运行）
                self.logger.debug("Session marked as closed but container kept running")
