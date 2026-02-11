"""多智能体实验实现

定义多智能体协作的实验执行逻辑。
"""

import logging
from typing import Any
from evomaster.core.exp import BaseExp
from evomaster.agent import BaseAgent
from evomaster.utils.types import TaskInstance


class MultiAgentExp(BaseExp):
    """多智能体实验类

    实现Planning Agent和Coding Agent的协作工作流：
    1. Planning Agent分析任务并制定计划
    2. Coding Agent根据计划执行代码任务
    """

    def __init__(self, planning_agent, coding_agent, config, exp_index):
        """初始化多智能体实验

        Args:
            planning_agent: Planning Agent 实例
            coding_agent: Coding Agent 实例
            config: EvoMasterConfig 实例
        """
        # 为了兼容基类，传入第一个agent（planning_agent）
        # 但实际使用时会使用多个agent
        super().__init__(planning_agent, config)
        self.planning_agent = planning_agent
        self.coding_agent = coding_agent
        self.logger = logging.getLogger(self.__class__.__name__)
        self.exp_index = exp_index

    @property
    def exp_name(self) -> str:
        """返回实验阶段名称"""
        return "MultiAgent"

    def run(self, task_description: str, task_id: str = "exp_001") -> dict:
        """运行多智能体实验

        工作流：
        1. Planning Agent分析任务并制定计划
        2. Coding Agent根据计划执行代码任务

        Args:
            task_description: 任务描述
            task_id: 任务 ID

        Returns:
            执行结果字典
        """
        self.logger.info("Starting multi-agent task execution")
        self.logger.info(f"Task: {task_description}")

        results = {
            'task_description': task_description,
            'planning_result': None,
            'coding_result': None,
            'status': 'running',
        }

        # 设置当前exp信息，用于trajectory记录
        # exp_name 从类名自动推断（MultiAgentExp -> MultiAgent）
        BaseAgent.set_exp_info(exp_name=self.exp_name, exp_index=self.exp_index)

        try:
            # Step 1: Planning Agent制定计划
            if self.planning_agent:
                self.logger.info("=" * 60)
                self.logger.info("Step 1: Planning Agent analyzing task...")
                self.logger.info("=" * 60)

                planning_task = TaskInstance(
                    task_id=f"{task_id}_planning",
                    task_type="planning",
                    description=task_description,
                    input_data={},
                )

                planning_trajectory = self.planning_agent.run(planning_task)
                results['planning_trajectory'] = planning_trajectory

                # 提取Planning Agent的回答
                planning_result = self._extract_agent_response(planning_trajectory)
                results['planning_result'] = planning_result

                self.logger.info("Planning completed")
                self.logger.info(f"Planning result: {planning_result[:200]}...")

            # Step 2: Coding Agent执行任务
            if self.coding_agent:
                self.logger.info("=" * 60)
                self.logger.info("Step 2: Coding Agent executing task...")
                self.logger.info("=" * 60)

                # 准备Coding Agent的用户提示词格式化参数
                # 使用prompt_format_kwargs来传递planning_result
                original_format_kwargs = self.coding_agent._prompt_format_kwargs.copy()
                self.coding_agent._prompt_format_kwargs.update({
                    'planning_result': results.get('planning_result', '')
                })

                # 创建任务实例
                coding_task = TaskInstance(
                    task_id=f"{task_id}_coding",
                    task_type="coding",
                    description=task_description,
                    input_data={},
                )

                coding_trajectory = self.coding_agent.run(coding_task)

                # 恢复原始格式化参数
                self.coding_agent._prompt_format_kwargs = original_format_kwargs

                # 提取Coding Agent的结果
                coding_result = self._extract_agent_response(coding_trajectory)
                results['coding_result'] = coding_result
                results['coding_trajectory'] = coding_trajectory

                self.logger.info("Coding completed")
                self.logger.info(f"Coding status: {coding_trajectory.status}")

            results['status'] = 'completed'
            self.logger.info("Multi-agent task execution completed")

            # 保存结果到 self.results（用于 save_results）
            result = {
                "task_id": task_id,
                "status": results['status'],
                "steps": 0,  # 多agent场景下steps计算方式不同
                "planning_trajectory": results.get('planning_trajectory'),
                "coding_trajectory": results.get('coding_trajectory'),
                "planning_result": results.get('planning_result'),
                "coding_result": results.get('coding_result'),
            }
            self.results.append(result)

        except Exception as e:
            self.logger.error(f"Multi-agent task execution failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

            # 保存失败结果
            result = {
                "task_id": task_id,
                "status": "failed",
                "steps": 0,
                "error": str(e),
            }
            self.results.append(result)

        return results

