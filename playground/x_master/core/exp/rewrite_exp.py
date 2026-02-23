import logging
import json
from typing import Any
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

from evomaster import TaskInstance
from evomaster.agent import BaseAgent
from evomaster.core.exp import BaseExp
from .utils import strip_think_and_exec, extract_agent_response


class RewriteExp(BaseExp):
    """X-Master中Rewrite实验类实现

    实现Rewrite阶段工作流：汇总前一模块的所有答案，重写相同数量的答案
    """

    @property
    def exp_name(self) -> str:
        """返回实验阶段名称"""
        return "Rewriting"

    def __init__(self, rewriter_agent,  config, index=0):
        """初始化RewriteExp实验类

        Args:
            rewriter_agent: Rewriter Agent 实例
            config: EvoMasterConfig 实例
            index: x-master需要并行多个exp, 因此需要为每个相同的exp定义一个编号
        """
        super().__init__(rewriter_agent, config)
        self.rewriter = rewriter_agent
        self.index = index
        self.logger = logging.getLogger(self.__class__.__name__)

        self.rewriter._current_exp_name = self.exp_name
        self.rewriter._current_exp_index = self.index
        

    def run(self, task_description:str,task_id:str = "exp_001",solutions:List[str]=None) -> dict:
        """运行rewriter实验

        工作流: 一个Rewriter Agent对前一个模块的所有答案进行汇总并重写

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
            self.logger.error(f"Rewriter-agent task execution failed: Solutions is None", exc_info=True)
            results['status'] = 'failed'
            results['error'] = "Solutions is None"
            return super().run(task_description, task_id)
        
        index = self.index

        try:
            if self.rewriter:
                self.logger.info("="*60)
                self.logger.info(f"Rewrite : Rewriting no.{index} solution ...")
                self.logger.info("=" * 60)

                rewriter_task = TaskInstance(
                    task_id = f"{task_id}_rewriter",
                    task_type = "rewriter",
                    description=task_description,
                    input_data={},
                )

                original_format_kwargs = self.rewriter._prompt_format_kwargs.copy()

                s_solutions = self._format_solutions_prompt(solutions)

                try:
                    # 设置当前exp信息，用于trajectory记录
                    self.rewriter._prompt_format_kwargs.update({
                        's_solutions':s_solutions
                    })
                    rewriter_trajectory = self.rewriter.run(rewriter_task)
                    results[f'rewriter_trajectory'] = rewriter_trajectory
                    rewriter_result = extract_agent_response(rewriter_trajectory)
                    results[f'rewriter_result'] = rewriter_result
                    self.rewriter.reset_context()
                    self.logger.info("Rewriting completed")


                except Exception as e:
                    print(f"Task {index} failed: {e}")
                    results[f'rewriter_trajectory'] = None
                    results[f'rewriter_result'] = None
                    self.logger.info("Rewriting failed")

                
                self.rewriter._prompt_format_kwargs = original_format_kwargs
            

                results['status'] = 'completed'

                self.logger.info("rewriter-agent task execution completed")

        except Exception as e:
            self.logger.error(f"rewriter-agent task execution failed: {e}", exc_info=True)
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
            ## Student 1's Solution
            {solution_1}
            ## Student 2's Solution
            {solution_2}
            ## Student 3's Solution
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
            prompt_lines.append(f"## Student {i}'s Solution")
            prompt_lines.append(clean_solution)
            prompt_lines.append("")

        return "\n".join(prompt_lines).strip()


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

        self.logger.info(f"RewriteExp(index:{self.index}) Results saved to {output_file}")

