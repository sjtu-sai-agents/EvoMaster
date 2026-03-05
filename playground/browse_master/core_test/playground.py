"""
Browse-Master Playground 实现

实现完整的 Plan-Execute 工作流：
1. PlannerExp 分析任务并输出 <task> 或 <answer>
2. ExecutorExp 执行 <task> 并返回 <results>
3. 循环直到 PlannerExp 输出 <answer>
"""

import logging
import sys
from pathlib import Path

# 确保可以导入 evomaster 模块
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground
from evomaster.utils.types import TaskInstance

from .exp import PlannerExp, ExecutorExp, extract_planner_answer, extract_tasks, extract_confidence


@register_playground("browse_master_test")
class BrowseMasterPlayground(BasePlayground):
    """BrowseMaster Playground

    协调 PlannerExp 和 ExecutorExp，实现迭代循环工作流。
    """

    def __init__(self, config_dir: str | Path | None = None, config_path: str | Path | None = None):
        """初始化 BrowseMaster Playground

        Args:
            config_dir: 配置目录路径，默认为 configs/agent/browse_master
            config_path: 配置文件完整路径
        """
        # 设置默认配置目录
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "agent" / "browse_master"

        # 调用父类初始化
        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)

        # 声明两个 Agent
        self.agents.declare("planner", "executor")

        # 初始化 mcp_manager（BasePlayground.cleanup 需要）
        self.mcp_manager = None

        # Exp 实例
        self.planner_exp = None
        self.executor_exp = None

    def setup(self) -> None:
        """初始化所有组件"""
        self.logger.info("Setting up Browse-Master playground...")
        self._setup_session()
        self._setup_agents()

        # 创建 Exp 实例
        self.planner_exp = PlannerExp(
            agent=self.agents.planner_agent,
            config=self.config
        )
        self.executor_exp = ExecutorExp(
            agent=self.agents.executor_agent,
            config=self.config
        )

        # 传递 run_dir 给 Exp
        if self.run_dir:
            self.planner_exp.set_run_dir(self.run_dir)
            self.executor_exp.set_run_dir(self.run_dir)

        self.logger.info("Browse-Master playground setup complete")

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        """运行 Browse-Master 工作流

        工作流程：
        1. PlannerExp 分析任务，输出 <task> 或 <answer>
        2. 如果是 <task>，ExecutorExp 执行并返回 <results>
        3. 将 Executor 结果反馈给 Planner，继续下一轮
        4. 直到 Planner 输出 <answer> 或达到最大轮次

        Args:
            task_description: 任务描述
            output_file: 结果保存文件（可选）

        Returns:
            运行结果字典
        """
        try:
            self.setup()

            # 设置轨迹文件路径
            self._setup_trajectory_file(output_file)

            self.logger.info("Starting Browse-Master workflow...")
            self.logger.info(f"Task: {task_description}")

            results = {
                'task_description': task_description,
                'status': 'running',
            }

            # 迭代循环
            round_num = 0
            max_rounds = 10
            final_answer = None

            while round_num < max_rounds:
                round_num += 1
                self.logger.info("=" * 60)
                self.logger.info(f"Round {round_num}: Planner analyzing...")
                self.logger.info("=" * 60)

                # Step 1: 运行 PlannerExp
                planner_result = self.planner_exp.run(
                    task_description=task_description,
                    task_id=f"planner_r{round_num}"
                )
                results[f'planner_result_{round_num}'] = planner_result['result']
                results[f'planner_trajectory_{round_num}'] = planner_result['trajectory']

                self.logger.info(f"Planner result: {planner_result['result'][:500]}...")

                # Step 2: 判断 Planner 输出类型
                if "<answer>" in planner_result['result']:
                    # 提取最终答案，结束循环
                    final_answer = extract_planner_answer(planner_result['result'])
                    confidence = extract_confidence(planner_result['result'])
                    results['final_answer'] = final_answer
                    results['confidence'] = confidence
                    self.logger.info("=" * 60)
                    self.logger.info(f"Final answer: {final_answer}")
                    self.logger.info(f"Confidence: {confidence}")
                    self.logger.info("=" * 60)
                    break

                elif "<task>" in planner_result['result']:
                    # 提取子任务（取最后一个）
                    tasks = extract_tasks(planner_result['result'])
                    search_target = tasks[-1] if tasks else ""

                    self.logger.info(f"Task assigned to Executor: {search_target}")

                    # Step 3: 运行 ExecutorExp
                    self.logger.info(f"Round {round_num}: Executor executing...")
                    executor_result = self.executor_exp.run(
                        search_target=search_target,
                        task_id=f"executor_r{round_num}"
                    )
                    results[f'executor_result_{round_num}'] = executor_result['result']
                    results[f'executor_trajectory_{round_num}'] = executor_result['trajectory']

                    self.logger.info(f"Executor result: {executor_result['result'][:500]}...")

                    # Step 4: 将 Executor 结果反馈给 Planner
                    feedback_content = (
                        f"Executor 执行结果:\n"
                        f"搜索目标：{search_target}\n"
                        f"结果：{executor_result['result']}"
                    )
                    self.agents.planner_agent.add_user_message(feedback_content)
                    self.logger.info("Fed executor result back to planner")

                else:
                    # 异常处理：既没有 task 也没有 answer
                    self.logger.warning("Neither <task> nor <answer> found in planner output")
                    results['status'] = 'failed'
                    results['error'] = "Neither <task> nor <answer> found in planner output"
                    break

            # 循环结束处理
            if final_answer is None:
                self.logger.warning(f"Max rounds ({max_rounds}) reached without final answer")
                results['status'] = 'incomplete'
                results['error'] = f"Max rounds ({max_rounds}) reached"
            else:
                results['status'] = 'completed'

            self.logger.info("Browse-Master workflow completed")
            return results

        finally:
            self.cleanup()
