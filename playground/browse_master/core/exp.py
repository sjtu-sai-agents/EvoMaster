"""
pe_exp 实现

实现 Planner 和 Executor 的工作流
"""

import logging
import re
from typing import Any, List
from evomaster.core.exp import BaseExp
from evomaster.agent import BaseAgent
from evomaster.utils.types import TaskInstance


def extract_planner_answer(text: str) -> str:
    """从 Planner 响应中提取最终答案

    首先尝试提取 <answer> 标签内容，
    其次提取 </think> 后的内容，
    最后返回原文本

    Args:
        text: Planner 响应文本

    Returns:
        提取的答案文本
    """
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


def extract_tasks(text: str) -> List[str]:
    """从 Planner 响应中提取所有任务

    Args:
        text: Planner 响应文本

    Returns:
        任务列表
    """
    task_pattern = r'<task>\s*(.*?)\s*</task>'
    matches = re.findall(task_pattern, text, re.DOTALL)
    return [match.strip() for match in matches]


class PlanExecuteExp(BaseExp):
    """多智能体实验类

    实现 Planner 和 Executor 的协作工作流：
    1. Planner 分析任务并制定计划
    2. Executor 根据计划调用工具执行代码任务
    """

    def __init__(self, planner, executor, config):
        """初始化多智能体实验

        Args:
            Planner: planner Agent 实例
            Executor: executor Agent 实例
            config: EvoMasterConfig 实例
        """
        # 为了兼容基类，传入第一个 agent（Planner）
        # 但实际使用时会使用多个 agent
        super().__init__(planner, config)
        self.planner = planner
        self.executor = executor
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def exp_name(self) -> str:
        """返回实验阶段名称"""
        return "PlanExecute"

    def run(self, task_description: str, task_id: str = "exp_001") -> dict:
        """运行多智能体实验

        工作流：
        1. Planner 分析任务并制定计划
        2. Executor 根据计划调用工具执行代码任务
        3. Planner 根据 Executor 反馈迭代，直到找到答案

        Args:
            task_description: 任务描述
            task_id: 任务 ID

        Returns:
            执行结果字典
        """
        self.logger.info("Starting plan-execute task execution")
        self.logger.info(f"Task: {task_description}")

        results = {
            'task_description': task_description,
            'status': 'running',
        }

        BaseAgent.set_exp_info(exp_name=self.exp_name, exp_index=0)

        try:
            round_num = 0
            max_rounds = 10  # 防止无限循环
            final_answer = None
            search_target = ""

            while round_num < max_rounds:
                round_num += 1
                self.logger.info("=" * 60)
                self.logger.info(f"Round {round_num}: Planner analyzing...")
                self.logger.info("=" * 60)

                # Step 1: Planner 制定计划/分析反馈
                planner_task = TaskInstance(
                    task_id=f"{task_id}_planner_r{round_num}",
                    task_type="planner",
                    description=task_description,
                    input_data={},
                )

                planner_trajectory = self.planner.run(planner_task)
                results[f'planner_trajectory_{round_num}'] = planner_trajectory

                # 提取 Planner 的回答
                planner_result = self._extract_agent_response(planner_trajectory)
                results[f'planner_result_{round_num}'] = planner_result

                self.logger.info(f"Planner round_{round_num} completed")
                self.logger.info(f"Planner result: {planner_result[:500]}...")

                # Step 2: 判断 Planner 输出类型
                if "<answer>" in planner_result:
                    # 提取最终答案，结束循环
                    final_answer = extract_planner_answer(planner_result)
                    results['final_answer'] = final_answer
                    self.logger.info("=" * 60)
                    self.logger.info(f"Final answer found: {final_answer}")
                    self.logger.info("=" * 60)
                    break
                elif "<task>" in planner_result:
                    # 提取子任务（取最后一个）
                    tasks = extract_tasks(planner_result)
                    search_target = tasks[-1] if tasks else ""

                    self.logger.info(f"Task assigned to Executor: {search_target}")

                    # Step 3: Executor 执行子任务（单轮）
                    executor_result = self._run_executor_loop(
                        search_target, round_num, task_id
                    )
                    results[f'executor_result_{round_num}'] = executor_result

                    # Step 4: 将 Executor 结果反馈给 Planner
                    self._feed_executor_result_to_planner(executor_result)
                else:
                    # 异常处理：既没有 task 也没有 answer
                    self.logger.warning("Neither <task> nor <answer> found in planner output")
                    results['status'] = 'failed'
                    results['error'] = "Neither <task> nor <answer> found in planner output"
                    break

            if final_answer is None:
                self.logger.warning(f"Max rounds ({max_rounds}) reached without final answer")
                results['status'] = 'incomplete'
                results['error'] = f"Max rounds ({max_rounds}) reached"
            else:
                results['status'] = 'completed'

            self.logger.info("PlanExecute task execution completed")

        except Exception as e:
            self.logger.error(f"plan-execute task execution failed: {e}", exc_info=True)
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

    def _run_executor_loop(self, search_target: str, round_num: int, task_id: str) -> dict:
        """运行 Executor 执行搜索任务（单轮）

        Args:
            search_target: 搜索目标
            round_num: 当前轮次
            task_id: 任务 ID

        Returns:
            Executor 执行结果字典
        """
        self.logger.info(f"Round {round_num}: Executor executing with target: {search_target}")

        # 设置 Executor 的搜索目标
        original_format_kwargs = self.executor._prompt_format_kwargs.copy()
        self.executor._prompt_format_kwargs.update({'search_target': search_target})

        try:
            # Executor 执行（单轮）
            executor_task = TaskInstance(
                task_id=f"{task_id}_executor_r{round_num}",
                task_type="executor",
                description=search_target,  # 使用搜索目标作为描述
                input_data={},
            )

            executor_trajectory = self.executor.run(executor_task)
            executor_result = self._extract_agent_response(executor_trajectory)

            return {
                'trajectory': executor_trajectory,
                'result': executor_result,
                'search_target': search_target,
                'round': round_num,
            }
        finally:
            # 恢复原始参数
            self.executor._prompt_format_kwargs = original_format_kwargs

    def _feed_executor_result_to_planner(self, executor_result: dict):
        """将 Executor 结果作为用户消息注入 Planner 上下文

        Args:
            executor_result: Executor 执行结果字典
        """
        feedback_content = (
            f"Executor 执行结果:\n"
            f"搜索目标：{executor_result.get('search_target', 'N/A')}\n"
            f"结果：{executor_result.get('result', 'N/A')}"
        )
        self.planner.add_user_message(feedback_content)
        self.logger.info("Fed executor result back to planner")

    def _extract_agent_response(self, trajectory: Any) -> str:
        """从轨迹中提取 Agent 的最终回答

        Args:
            trajectory: 执行轨迹

        Returns:
            Agent 的回答文本
        """
        if not trajectory or not trajectory.dialogs:
            return ""

        # 获取最后一个对话
        last_dialog = trajectory.dialogs[-1]

        # 查找最后一个助手消息
        for message in reversed(last_dialog.messages):
            if hasattr(message, 'role') and message.role.value == 'assistant':
                if hasattr(message, 'content') and message.content:
                    return message.content

        return ""
