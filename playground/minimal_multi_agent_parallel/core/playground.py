"""多智能体 Playground 实现

展示如何使用多个Agent协作完成任务。
包含Planning Agent和Coding Agent的工作流。
"""

import logging
import sys
from pathlib import Path

# 确保可以导入evomaster模块
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evomaster.agent import Agent

from .exp import MultiAgentExp
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from typing import List, Any, Callable

@register_playground("minimal_multi_agent_parallel")
class MultiAgentParallelPlayground(BasePlayground):
    """多智能体 Playground

    实现Planning Agent和Coding Agent的协作工作流：
    1. Planning Agent分析任务并制定计划
    2. Coding Agent根据计划执行代码任务

    使用方式：
        # 通过统一入口
        python run.py --agent minimal_multi_agent --task "任务描述"

        # 或使用独立入口
        python playground/minimal_multi_agent/main.py
    """

    def __init__(self, config_dir: Path = None, config_path: Path = None):
        """初始化多智能体 Playground

        Args:
            config_dir: 配置目录路径，默认为 configs/minimal_multi_agent/
            config_path: 配置文件完整路径（如果提供，会覆盖 config_dir）
        """
        if config_path is None and config_dir is None:
            # 默认配置目录
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "agent" / "minimal_multi_agent"

        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.agents.declare("planning_agent", "coding_agent")

        # 从配置中读取并行配置
        session_config = self.config.session.get("local", {})
        parallel_config = session_config.get("parallel", {})
        if parallel_config.get("enabled", False):
            self.max_workers = parallel_config.get("max_parallel", 3)
        else:
            self.max_workers = 3
        
        # 初始化mcp_manager（BasePlayground.cleanup需要）
        self.mcp_manager = None

    def setup(self) -> None:
        self.logger.info("Setting up minimal multi-agent parallel playground...")

        self._setup_session()
        self._setup_agents()

        self.logger.info("Minimal multi-agent parallel playground setup complete")

    def _create_exp(self, exp_index):
        """创建多智能体实验实例

        覆盖基类方法，创建 MultiAgentExp 实例。
        为每个 exp 创建独立的 Agent 副本，确保并行运行时上下文不冲突。

        Args:
            exp_index: 实验索引

        Returns:
            MultiAgentExp 实例
        """
        # 为每个 exp 创建独立的 Agent 副本
        # 每个 agent 副本拥有独立的 LLM 实例（不共享），避免并行时的冲突
        # 共享 session, tools, skill_registry 等配置，但拥有独立的上下文
        planning_agent_copy = self.copy_agent(
            self.agents.planning_agent, 
            new_agent_name=f"planning_exp_{exp_index}"
        ) if self.agents.planning_agent else None
        
        coding_agent_copy = self.copy_agent(
            self.agents.coding_agent, 
            new_agent_name=f"coding_exp_{exp_index}"
        ) if self.agents.coding_agent else None
        
        exp = MultiAgentExp(
            planning_agent=planning_agent_copy,
            coding_agent=coding_agent_copy,
            config=self.config,
            exp_index=exp_index
        )
        # 传递 run_dir 给 Exp
        if self.run_dir:
            exp.set_run_dir(self.run_dir)
        return exp


    def run(self, task_description: str, output_file: str | None = None) -> dict:
        """运行工作流（覆盖基类方法）

        Args:
            task_description: 任务描述
            output_file: 结果保存文件（可选，如果设置了 run_dir 则自动保存到 trajectories/）

        Returns:
            运行结果
        """
        try:
            self.setup()
            self._setup_trajectory_file(output_file)
            task_description_1 = task_description
            task_description_2 = task_description
            task_description_3 = task_description
            # --- 关键步骤：创建任务列表 ---
            task_descriptions = [task_description_1, task_description_2, task_description_3]
            tasks = []
            for i in range(self.max_workers):
                exp = self._create_exp(exp_index=i)
                
                task_func = partial(exp.run, task_description=task_descriptions[i])
                
                tasks.append(task_func)
            
            # --- 调用封装好的并行函数 ---
            results = self.execute_parallel_tasks(tasks, max_workers=self.max_workers)
            
            result = {
                "status": "completed",
                "steps": 0,
            }
            return result

        finally:
            self.cleanup()


