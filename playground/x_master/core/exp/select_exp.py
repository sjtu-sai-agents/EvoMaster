import logging
import json
import re
from typing import Any
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

from evomaster import TaskInstance
from evomaster.agent import BaseAgent
from evomaster.core.exp import BaseExp
from .utils import strip_think_and_exec, extract_agent_response


class SelectExp(BaseExp):
    """X-Master中Select实验类实现

    实现Select阶段工作流：汇总前一模块的所有答案，选择最佳的答案
    """

    @property
    def exp_name(self) -> str:
        """返回实验阶段名称"""
        return "Selecting"

    def __init__(self, selector_agent,  config , index=0):
        """初始化SelectExp实验类

        Args:
            selector_agent: Selector Agent 实例
            config: EvoMasterConfig 实例
            index: x-master需要并行多个exp, 因此需要为每个相同的exp定义一个编号
        """

        super().__init__(selector_agent, config)
        self.selector = selector_agent
        self.index = index
        self.logger = logging.getLogger(self.__class__.__name__)

        self.selector._current_exp_name = self.exp_name
        self.selector._current_exp_index = self.index

    def run(self, task_description:str,task_id:str = "exp_001", solutions:List[str] = None) -> dict:
            """运行Selector实验

            工作流: 一个Selector Agent汇总前一个模块的所有答案并选择最佳答案

            Args:
                task_description: 任务描述
                task_id: 任务 ID
                solutions: 接收到来自前一个模块的所有答案
            Returns:
                执行结果字典
            """
            results = {
                'task_id':task_id,
                'steps':0,
                'task_description': task_description,
                'exp_index': self.index,
                'status': 'running',
            }
            if solutions is None:
                self.logger.error(f"selector-agent task execution failed: Solutions is None", exc_info=True)
                results['status'] = 'failed'
                results['error'] = "Solutions is None"
                return super().run(task_description, task_id)


            try:
                if self.selector:
                    self.logger.info("="*60)
                    self.logger.info("Selector : Selecting the best solution...")
                    self.logger.info("=" * 60)

                    selector_task = TaskInstance(
                        task_id = f"{task_id}_selector",
                        task_type = "selector",
                        description=task_description,
                        input_data={},
                    )

                    original_format_kwargs = self.selector._prompt_format_kwargs.copy()

                    # 格式化 solutions（使用 strip_think_and_exec 清理）
                    responses = self._format_solutions_prompt(solutions)

                    try:
                        # 设置当前exp信息，用于trajectory记录
                        BaseAgent.set_exp_info(exp_name=self.exp_name, exp_index=0)
                        self.selector._prompt_format_kwargs.update({
                            'Responses':responses
                        })
                        selector_trajectory = self.selector.run(selector_task)
                        results['selector_trajectory'] = selector_trajectory

                        # 提取 LLM 的原始回复
                        selector_response = extract_agent_response(selector_trajectory)
                        results['selector_response'] = selector_response

                        # 解析选择结果，返回最终选中的答案
                        selected_solution = self._parse_selector_choice(selector_response, solutions)
                        results['selector_result'] = selected_solution
                        results['selected_index'] = self._get_selected_index(selector_response, len(solutions))
                        
                        self.logger.info("Selecting completed")
                    except Exception as e:
                        self.logger.error(f"Selector task failed: {e}", exc_info=True)
                        results['selector_trajectory'] = None
                        results['selector_result'] = None
                        self.logger.info("Selecting failed")

                    self.selector._prompt_format_kwargs = original_format_kwargs


                    results['status'] = 'completed'
                    self.logger.info("Selector-agent task execution completed")

            except Exception as e:
                self.logger.error(f"Selector-agent task execution failed: {e}", exc_info=True)
                results['status'] = 'failed'
                results['error'] = str(e)

            self.results.append(results)
            return results

    def _format_solutions_prompt(self, solutions:List[str]) -> str:
        """格式化解决方案列表为prompt

        Args:
            solutions: 方案列表
        Reture:
            返回的方案prompt:
            格式：
            ## Respnse 1
            {solution_1}
            ## Respnse 2
            {solution_2}
            ## Respnse 3
            {solution_3}
            ...
            ...
        """

        if not solutions:
            return "No solutions"

        prompt_lines = []
        for i, solution in enumerate(solutions,1):
            # 使用 strip_think_and_exec 清理每个 solution
            clean_solution = strip_think_and_exec(solution)
            if not clean_solution:
                clean_solution = "empty solution"
            prompt_lines.append(f"## Response {i}")
            prompt_lines.append(clean_solution)
            prompt_lines.append("")

        return "\n".join(prompt_lines).strip()

    def _parse_selector_choice(self, selector_response: str, solutions: List[str]) -> str:
        """从 Selector 的回复中解析选择的答案

        解析 <select>Response X</select> 标签，返回对应的原始 solution

        Args:
            selector_response: Selector Agent 的回复文本
            solutions: 原始 solutions 列表

        Returns:
            选中的 solution 原文
        """
        if not selector_response or not solutions:
            self.logger.warning("Empty selector_response or solutions, returning first solution")
            return solutions[0] if solutions else ""

        # 正则匹配 <select>Response X</select>
        match = re.search(r'<select>Response\s*(\d+)</select>', selector_response, re.IGNORECASE)
        if not match:
            self.logger.warning("Could not parse selector's decision. Defaulting to Response 1.")
            return solutions[0]

        idx = int(match.group(1)) - 1  # 转换为 0-based 索引
        # 确保索引在有效范围内
        idx = max(0, min(len(solutions) - 1, idx))

        self.logger.info(f"Selector chose Response {idx + 1}")
        return solutions[idx]

    def _get_selected_index(self, selector_response: str, num_solutions: int) -> int:
        """从 Selector 的回复中提取选择的索引

        Args:
            selector_response: Selector Agent 的回复文本
            num_solutions: solutions 的数量

        Returns:
            选中的索引（0-based），解析失败返回 0
        """
        if not selector_response:
            return 0

        match = re.search(r'<select>Response\s*(\d+)</select>', selector_response, re.IGNORECASE)
        if not match:
            return 0

        idx = int(match.group(1)) - 1
        return max(0, min(num_solutions - 1, idx))



    def save_results(self, output_file: str):
        """保存实验结果

        Args:
            output_file: 输出文件路径
        """
        import json
        from pathlib import Path


        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, default=str, ensure_ascii=False)

        self.logger.info(f"SelectExp(index:{self.index}) Results saved to {output_file}")

