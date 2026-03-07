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
        self.final_found = False

        try:
            # Step 1: Planning Agent制定计划
            if self.planner:
                self.logger.info("=" * 60)
                self.logger.info("Step 1: Planning Agent analyzing task...")
                self.logger.info("=" * 60)

                planner_task = TaskInstance(
                    task_id=f"{task_id}_planner",
                    task_type="planner",
                    description=task_description,
                    input_data={},
                )

                planner_trajectory = self.planner.run(planner_task)
                results['planner_trajectory'] = planner_trajectory

                # 提取Planning Agent的回答
                planner_result = self._extract_agent_response(planner_trajectory)
                results['planner_result'] = planner_result

                self.logger.info("Planning completed")
                self.logger.info(f"Planning result: {planner_result[:200]}...")

                # Step 2: 判断 Planner 输出类型
                if "<answer>" in planner_result:
                    # 提取最终答案，结束循环
                    final_answer = extract_planner_answer(planner_result)
                    results['final_answer'] = final_answer
                    results['final_found'] = 1
                    self.logger.info("=" * 60)
                    self.logger.info(f"Final answer found: {final_answer}")
                    self.logger.info("=" * 60)
                    self.final_found = True

                elif "<task>" in planner_result:
                    # 提取子任务
                    tasks = extract_tasks(planner_result)
                    results['final_found'] = 0
                    search_target = tasks[-1] if tasks else ""
                    results['search_target'] = search_target
                    self.logger.info(f"Task assigned to Executor: {search_target}")

                else:
                    # 异常处理：既没有 task 也没有 answer
                    self.logger.warning("Neither <task> nor <answer> found in planner output")
                    results['final_found'] = 0
                    results['status'] = 'failed'
                    results['error'] = "Neither <task> nor <answer> found in planner output"
                    

            # Step 2: Coding Agent执行任务
            if self.final_found == False :
                if self.executor:
                    self.logger.info("=" * 60)
                    self.logger.info("Step 2: Coding Agent executing task...")
                    self.logger.info("=" * 60)

                    # 准备Coding Agent的用户提示词格式化参数
                    # 使用prompt_format_kwargs来传递search_target
                    original_format_kwargs = self.executor._prompt_format_kwargs.copy()
                    self.executor._prompt_format_kwargs.update({
                        'search_target': results.get('search_target')
                    })

                    # 创建任务实例
                    executor_task = TaskInstance(
                        task_id=f"{task_id}_executor",
                        task_type="executor",
                        description=task_description,
                        input_data={},
                    )

                    executor_trajectory = self.executor.run(executor_task)

                    # 恢复原始格式化参数
                    self.executor._prompt_format_kwargs = original_format_kwargs

                    # 提取Coding Agent的结果
                    executor_result = self._extract_agent_response(executor_trajectory)
                    results['executor_result'] = executor_result
                    results['executor_trajectory'] = executor_trajectory

                    self.logger.info("Coding completed")
                    self.logger.info(f"Coding status: {executor_trajectory.status}")

                results['status'] = 'completed'
                self.logger.info("Multi-agent task execution completed")

                # 保存结果到 self.results（用于 save_results）
                result = {
                    "task_id": task_id,
                    "status": results['status'],
                    "steps": 0,  # 多agent场景下steps计算方式不同
                    "final_found": 0,
                    "planner_trajectory": results.get('planner_trajectory'),
                    "executor_trajectory": results.get('executor_trajectory'),
                    "search_target": results.get('search_target'),
                    "planner_result": results.get('planner_result'),
                    "executor_result": results.get('executor_result'),
                }
                self.results.append(result)
            else :
                results['status'] = 'completed'
                self.logger.info("Multi-agent task execution completed")

                # 保存结果到 self.results（用于 save_results）
                result = {
                    "task_id": task_id,
                    "status": results['status'],
                    "steps": 0,  # 多agent场景下steps计算方式不同
                    "final_found": 1,
                    "final_answer": results.get('final_answer'),
                    "planner_trajectory": results.get('planner_trajectory'),
                    # "executor_trajectory": results.get('executor_trajectory'),
                    "planner_result": results.get('planner_result'),
                    # "executor_result": results.get('executor_result'),
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

    # def _feed_executor_result_to_planner(self, executor_result: dict):
    #     """将 Executor 结果作为用户消息注入 Planner 上下文

    #     Args:
    #         executor_result: Executor 执行结果字典
    #     """
    #     feedback_content = (
    #         f"Executor 执行结果:\n"
    #         f"搜索目标：{executor_result.get('search_target', 'N/A')}\n"
    #         f"结果：{executor_result.get('result', 'N/A')}"
    #     )
    #     self.planner.add_user_message(feedback_content)
    #     self.logger.info("Fed executor result back to planner")
