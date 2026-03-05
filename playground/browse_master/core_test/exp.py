"""
Browse-Master Exp 实现

包含两个独立的 Exp 类：
- PlannerExp：负责分析和规划，输出 <task> 或 <answer>
- ExecutorExp：负责执行搜索任务，输出 <results>
"""

import logging
import re
from typing import Any, List
from evomaster.core.exp import BaseExp
from evomaster.agent import BaseAgent
from evomaster.utils.types import TaskInstance


def extract_planner_answer(text: str) -> str:
    """从 Planner 响应中提取最终答案"""
    pattern = r'<answer>\s*((?:(?!</answer>).)*?)</answer>'
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


def extract_executor_answer(text: str) -> str:
    """从 Executor 响应中提取结果"""
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


def extract_tasks(text: str) -> List[str]:
    """从 Planner 响应中提取所有任务"""
    task_pattern = r'<task>\s*(.*?)\s*</task>'
    matches = re.findall(task_pattern, text, re.DOTALL)
    return [match.strip() for match in matches]


def extract_confidence(text: str) -> str:
    """从 Planner 响应中提取置信度"""
    pattern = r'<confidence>\s*((?:(?!</confidence>).)*?)</confidence>'
    matches = list(re.finditer(pattern, text, re.DOTALL))
    if matches:
        return matches[-1].group(1).strip()
    return "N/A"


class PlannerExp(BaseExp):
    """Planner 实验类

    负责分析问题并制定计划：
    - 输出 <task> 委托给 Executor
    - 输出 <answer> 表示找到最终答案
    """

    @property
    def exp_name(self) -> str:
        return "Planner"

    def run(self, task_description: str, task_id: str = "planner_001") -> dict:
        """运行 Planner 单次执行

        Args:
            task_description: 任务描述
            task_id: 任务 ID

        Returns:
            执行结果字典
        """
        self.logger.info(f"Planner running with task: {task_description[:200]}...")

        BaseAgent.set_exp_info(exp_name=self.exp_name, exp_index=0)

        # 创建任务实例
        task = TaskInstance(
            task_id=task_id,
            task_type="planner",
            description=task_description,
            input_data={},
        )

        # 运行 Planner Agent
        trajectory = self.agent.run(task)

        # 提取响应
        result_text = self._extract_agent_response(trajectory)

        return {
            'trajectory': trajectory,
            'result': result_text,
            'status': 'completed',
        }


class ExecutorExp(BaseExp):
    """Executor 实验类

    负责执行具体的搜索任务：
    - 接收 search_target
    - 调用工具执行搜索
    - 输出 <results>
    """

    @property
    def exp_name(self) -> str:
        return "Executor"

    def run(self, search_target: str, task_id: str = "executor_001") -> dict:
        """运行 Executor 单次执行

        Args:
            search_target: 搜索目标
            task_id: 任务 ID

        Returns:
            执行结果字典
        """
        self.logger.info(f"Executor running with target: {search_target}")

        BaseAgent.set_exp_info(exp_name=self.exp_name, exp_index=0)
        
        # 保存原始参数
        original_format_kwargs = self.agent._prompt_format_kwargs.copy()

        try:
            # 设置搜索目标
            self.agent._prompt_format_kwargs.update({'search_target': search_target})

            # 创建任务实例
            task = TaskInstance(
                task_id=task_id,
                task_type="executor",
                description=search_target,
                input_data={},
            )

            # 运行 Executor Agent
            trajectory = self.agent.run(task)

            # 提取响应
            result_text = self._extract_agent_response(trajectory)

            return {
                'trajectory': trajectory,
                'result': result_text,
                'search_target': search_target,
                'status': 'completed',
            }
        finally:
            # 恢复原始参数
            self.agent._prompt_format_kwargs = original_format_kwargs
