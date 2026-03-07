"""Plan-Execute Playground 实现

实现完整的Plan-Execute工作流：
1. planner: 生成执行计划
2. executor: 执行计划并返回结果

每个阶段使用对应的Exp类，每个Exp会调用同一个Agent多次（并行执行）。
"""

import logging
import sys
import re
from pathlib import Path

# 确保可以导入evomaster模块
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evomaster.agent import Agent

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
        self.logger = logging.getLogger(self.__class__.__name__)
        # 存储两个组件的Agent
        self.agents.declare("planner","executor")
        
        # 初始化mcp_manager（BasePlayground.cleanup需要）
        self.mcp_manager = None
        
    
    def setup(self) -> None:
        """初始化所有组件

        覆盖基类方法，复用基类的公共方法来创建多个Agent。
        每个Agent使用独立的LLM实例，确保日志记录独立。
        """
        self.logger.info("Setting up Browse-Master playground...")
        self._setup_session()
        self._setup_agents()
        # self.agents.planner=self._create_agent("planner")
        # self.agents.executor=self._create_agent("executor")
        self.logger.info("Browse-Master playground setup complete")
    
    
    def _create_exp(self):
        """创建多智能体实验实例

        覆盖基类方法，创建 MultiAgentExp 实例。

        Returns:
            MultiAgentExp 实例
        """
        exp = PlanExecuteExp(
            planner=self.agents.planner_agent,    
            executor=self.agents.executor_agent,
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

            max_round = 10
            executor_result = None
            answer_list = []
            for _ in range(max_round) :
                if executor_result != None :
                    new_task_description = task_description.join(executor_result)
                else :
                    new_task_description = "总任务：".join(task_description)

                if task_id:
                    result = exp.run(new_task_description, task_id=task_id)
                else:
                    result = exp.run(new_task_description)
                
                if result['final_found'] == 1 :
                    final_answer = result['final_answer']
                    self.logger.info(f"Final answer: {final_answer}")
                    break

                else :
                    tmp_answer = extract_executor_answer(result['executor_result'])
                    answer_list.append(tmp_answer)
                    answer_list_str = "".join(answer_list)
                    executor_result = f"以下是先前的分析记录：{answer_list_str}"

            return result

        finally:
            self.cleanup()

def extract_executor_answer(text: str) -> str:
    """从 Executor 响应中提取结果

    首先尝试提取 <results> 标签内容，
    其次提取 </think> 后的内容，
    最后返回原文本

    Args:
        text: Executor 响应文本

    Returns:
        提取的结果文本
    """
    pattern = r'<results>\s*((?:(?!</results>).)*?)</results>'
    matches = list(re.finditer(pattern, text, re.DOTALL))
    if matches:
        return matches[-1].group(1).strip()
    else:
        pattern = r'</think>\s*(.*?)$'
        matches = list(re.finditer(pattern, text, re.DOTALL))
        if matches:
            return matches[-1].group(1).strip()
        else:
            return text.strip()