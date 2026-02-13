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


class CritiqueExp(BaseExp):
    """X-Master中Critique实验类实现

    实现Critique阶段工作流：分析初始结果并改进后得到优化后的结果
    """

    @property
    def exp_name(self) -> str:
        """返回实验阶段名称"""
        return "Critiquing"

    def __init__(self, critic_agent,  config, index=0):
        """初始化CritiqueExp实验类

        Args:
            critic_agent: Critic Agent 实例
            config: EvoMasterConfig 实例
            index: x-master需要并行多个exp, 因此需要为每个相同的exp定义一个编号
        """
        super().__init__(critic_agent, config)
        self.critic = critic_agent
        self.index = index
        self.logger = logging.getLogger(self.__class__.__name__)

        self.critic._current_exp_name = self.exp_name
        self.critic._current_exp_index = self.index

    def run(self, task_description:str,task_id:str = "exp_001",solution:str = None) -> dict:
        """运行critic实验

        工作流: 一个Critic Agent对初始答案进行更正生成

        Args:
            task_description: 任务描述
            task_id: 任务 ID
            solution: 接收到来自前一个模块的答案
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
        if solution is None:
            self.logger.error(f"Critic-agent task execution failed: Solution is None", exc_info=True)
            results['status'] = 'failed'
            results['error'] = "Solution is None"
            return super().run(task_description, task_id)

        index = self.index

        try:
            if self.critic:
                self.logger.info("="*60)
                self.logger.info(f"Critic : Critiquing no.{index} solution ...")
                self.logger.info("=" * 60)

                critic_task = TaskInstance(
                    task_id = f"{task_id}_critic",
                    task_type = "critic",
                    description=task_description,
                    input_data={},
                )
                original_format_kwargs = self.critic._prompt_format_kwargs.copy()

                try:
                    # 使用 strip_think_and_exec 清理上游 solution
                    cleaned_solution = strip_think_and_exec(solution)
                    self.critic._prompt_format_kwargs.update({
                        's_solution': cleaned_solution
                    })
                    critic_trajectory = self.critic.run(critic_task)
                    results[f'critic_trajectory'] = critic_trajectory
                    critic_result = extract_agent_response(critic_trajectory)
                    results[f'critic_result'] = critic_result
                    self.critic.reset_context()
                    self.logger.info("Criticting completed")


                except Exception as e:
                    print(f"Task {index} failed: {e}")
                    results[f'critic_trajectory'] = None
                    results[f'critic_result'] = None
                    self.logger.info("Criticting failed")

                
                self.critic._prompt_format_kwargs = original_format_kwargs

            
            results['status'] = 'completed'

            self.logger.info("Critic-agent task execution completed")

        except Exception as e:
            self.logger.error(f"Critic-agent task execution failed: {e}", exc_info=True)
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

        self.logger.info(f"CritiqueExp(index:{self.index}) Results saved to {output_file}")

