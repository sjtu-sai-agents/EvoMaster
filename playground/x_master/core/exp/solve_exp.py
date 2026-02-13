import logging
import json
from typing import Any
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from evomaster import TaskInstance
from evomaster.agent import BaseAgent
from evomaster.core.exp import BaseExp
from .utils import extract_agent_response

class SolveExp(BaseExp):
    """X-Master中Solve实验类实现

    实现Solve阶段工作流：分析任务并得到问题结果
    """

    @property
    def exp_name(self) -> str:
        """返回实验阶段名称"""
        return "Solving"

    def __init__(self, solver_agent, config, index=0):
        """初始化SolveExp实验类

        Args:
            solver_agent: Solver Agent 实例
            config: EvoMasterConfig 实例
            index: x-master需要并行多个exp, 因此需要为每个相同的exp定义一个编号
        """

        super().__init__(solver_agent, config)
        self.index = index
        self.solver = solver_agent
        self.logger = logging.getLogger(self.__class__.__name__)

        self.solver._current_exp_name = self.exp_name
        self.solver._current_exp_index = self.index

    def run(self, task_description:str, task_id:str = "exp_001") -> dict:
        """运行solver实验

        工作流: 一个Agent对同一个原始问题进行分析并得到初始答案

        Args:
            task_description: 任务描述
            task_id: 任务 ID
        
        Returns:
            执行结果字典
        """
        self.logger.info("Starting XMaster task execution")
        self.logger.info(f"Task:{task_description}")

        results = {
            'task_id':task_id,
            'steps':0,
            'task_description': task_description,
            'exp_index': self.index,
            'status': 'running',
        } 
        index = self.index

        try:
            if self.solver:
                self.logger.info("="*60)
                self.logger.info(f"Solver : Generating no.{index} solution in parallel...")
                self.logger.info("=" * 60)

                solver_task = TaskInstance(
                    task_id = f"{task_id}_solver",
                    task_type = "solver",
                    description=task_description,
                    input_data={},
                )
                try:
                    # 设置当前exp信息，用于trajectory记录
                    solver_trajectory = self.solver.run(solver_task)
                    results[f'solver_trajectory'] = solver_trajectory
                    solver_result = extract_agent_response(solver_trajectory)
                    results[f'solver_result'] = solver_result
                    self.solver.reset_context()

                    self.logger.info("Solving completed")

                except Exception as e:
                    print(f"Task {index} failed: {e}")
                    results[f'solver_trajectory'] = None
                    results[f'solver_result'] = None

                    self.logger.info("Solving failed")
            
                results['status'] = 'completed'
                self.logger.info("Solver-agent task execution completed")

        except Exception as e:
            self.logger.error(f"Solver-agent task execution failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)
        
        self.results.append(results)

        return results



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

        self.logger.info(f"SolveExp(index:{self.index}) Results saved to {output_file}")
