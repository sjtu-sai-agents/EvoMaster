"""Plan-Execute Playground 实现

实现完整的Plan-Execute工作流：
1. planner: 生成执行计划
2. executor: 执行计划并返回结果

每个阶段使用对应的Exp类，每个Exp会调用同一个Agent多次（并行执行）。
"""

import logging
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# 确保可以导入evomaster模块
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground
from evomaster import TaskInstance

from .exp import PlanExecuteExp

@register_playground("browse_master")
class BrowseMasterPlayground(BasePlayground):
    """BrowseMaster Playground
    
    协调PlanExp和ExecuteExp类，实现完整的Plan-Execute工作流。
    """
    
    def __init__(self, config_dir: str | Path | None = None, config_path: str | Path | None = None):
        """初始化BrowseMaster Playground
        
        Args:
            config_dir: 配置目录路径，默认为 configs/agent/browse_master
            config_path: 配置文件完整路径
        """
        # 设置默认配置目录（兼容 str/Path 类型）
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "agent" / "browse_master"
        
        # 必须先调用父类初始化（核心：初始化logger/config_manager/session等）
        super().__init__(config_dir=config_dir, config_path=config_path)
        
        # 存储两个组件的Agent
        self.planner = None
        self.executor = None
        
        # # 存储Exp实例
        # self.plan_exp = None
        # self.execute_exp = None
        
        # # 存储中间结果
        # self.plan_results = None
        # self.execute_results = None
        
        # 工作流配置
        self.agent_num = 5  # 每个Exp并行执行的Agent数量
        self.max_workers = 5  # 线程池大小
    
    def setup(self) -> None:
        """初始化所有组件

        覆盖基类方法，复用基类的公共方法来创建多个Agent。
        每个Agent使用独立的LLM实例，确保日志记录独立。
        """
        self.logger.info("Setting up Browse-Master playground...")

        # 1. 准备 LLM 配置（每个Agent会创建独立的LLM实例）
        llm_config_dict = self._setup_llm_config()
        self._llm_config_dict = llm_config_dict  # 保存配置供后续使用

        # 2. 创建 Session（所有Agent共享）
        self._setup_session()

        # 3. 创建工具注册表
        self._setup_tools()

        # 4. 创建多个Agent（每个Agent使用独立的LLM实例）
        self._setup_agents(llm_config_dict)

        self.logger.info("Browse-Master playground setup complete")
    
    def _setup_agents(self, llm_config_dict: Dict[str, Any]) -> None:
        """创建两个Agent
        
        Args:
            llm_config_dict: LLM配置字典
        """
        agents_config = getattr(self.config, 'agents', {})
        if not agents_config:
            raise ValueError(
                "No agents configuration found. "
                "Please add 'agents' section to config.yaml"
            )

        # 创建planner Agent（使用独立的LLM实例）
        if 'planner' in agents_config:
            planner_config = agents_config['planner']
            self.planner = self._create_agent(
                name="planner",
                agent_config=planner_config,
                enable_tools=planner_config.get('enable_tools', False),
                llm_config_dict=llm_config_dict,
                # skill_registry=skill_registry,  # 传递 skill_registry
            )
            self.logger.info("planner Agent created")

        # 创建Coding Agent（使用独立的LLM实例）
        if 'executor' in agents_config:
            executor_config = agents_config['executor']
            self.executor = self._create_agent(
                name="executor",
                agent_config=executor_config,
                enable_tools=executor_config.get('enable_tools', True),
                llm_config_dict=llm_config_dict,
                # skill_registry=skill_registry,  # 传递 skill_registry
            )
            self.logger.info("executor Agent created")  
    
    def _create_exp(self):
        """创建多智能体实验实例

        覆盖基类方法，创建 MultiAgentExp 实例。

        Returns:
            MultiAgentExp 实例
        """
        exp = PlanExecuteExp(
            planner=self.planner,
            executor=self.executor,
            config=self.config
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

            # 设置轨迹文件路径
            self._setup_trajectory_file(output_file)

            # 创建并运行实验
            exp = self._create_exp()

            self.logger.info("Running experiment...")
            # 如果有 task_id，传递给 exp.run()
            task_id = getattr(self, 'task_id', None)
            if task_id:
                result = exp.run(task_description, task_id=task_id)
            else:
                result = exp.run(task_description)

            return result

        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """清理资源（先清理自定义组件，再调用父类cleanup）"""
        self.logger.info("Cleaning up Browse-Master playground...")

        # 清理Agent实例（重置引用）
        self.planner = None
        self.executor = None

        super().cleanup()

        self.logger.info("Browse-Master playground cleanup complete")