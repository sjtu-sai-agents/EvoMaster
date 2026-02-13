"""
pe_exp实现

实现Planner和Executor的工作流
"""

import logging
from typing import Any
from evomaster.core.exp import BaseExp
from evomaster.agent import BaseAgent
from evomaster.utils.types import TaskInstance

class PlanExecuteExp(BaseExp):
    """多智能体实验类

    实现Planner和Executor的协作工作流：
    1. Planner分析任务并制定计划
    2. Executor根据计划调用工具执行代码任务
    """

    def __init__(self, planner, executor, config):
        """初始化多智能体实验

        Args:
            Planner: planner Agent 实例
            Executor: Coding Agent 实例
            config: EvoMasterConfig 实例
        """
        # 为了兼容基类，传入第一个agent（Planner）
        # 但实际使用时会使用多个agent
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
        1. Planner分析任务并制定计划
        2. Executor根据计划调用工具执行代码任务

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

        try:
            i = 1
            search_target = ""

            if self.planner:
                self.logger.info("=" * 60)
                self.logger.info(f"Planner Agent analyzing task (Round {i})")
                self.logger.info("=" * 60)

                planner_task = TaskInstance(
                    task_id=f"{task_id}_planner",
                    task_type="planner",
                    description=task_description,
                    input_data={},
                )

                planner_trajectory = self.planner.run(planner_task)
                results[f'planner_trajectory_{i}'] = planner_trajectory
                
                # 提取planner Agent的回答
                planner_result = self._extract_agent_response(planner_trajectory)
                results[f'planner_result_{i}'] = planner_result

                if "<task>" in planner_result:
                    search_target = planner_result.replace('<task>', '').replace('</task>', '').strip()
                
                self.logger.info(f"Planner round_{i} completed")
                self.logger.info(f"Planner result: {planner_result[:200]}...")

            while True:
                if self.executor:
                    self.logger.info("=" * 60)
                    self.logger.info(f"Executor Agent analyzing task (Round {i})")
                    self.logger.info("=" * 60)

                    original_format_kwargs = self.executor._prompt_format_kwargs.copy()
                    self.executor._prompt_format_kwargs.update({
                        'search_target': search_target
                    })

                    executor_task = TaskInstance(
                        task_id=f"{task_id}_executor",
                        task_type="executor",
                        description=task_description,
                        input_data={},
                    )
                    
                    executor_trajectory = self.executor.run(executor_task)
                    self.executor._prompt_format_kwargs = original_format_kwargs
                    results[f'executor_trajectory_{i}'] = executor_trajectory
                    
                    # 提取executor Agent的回答
                    executor_result = self._extract_agent_response(executor_trajectory)
                    results[f'executor_result_{i}'] = executor_result

                    self.logger.info(f"Executor round_{i} completed")
                    self.logger.info(f"Executor result: {executor_result[:200]}...")

                if self.planner:
                    self.logger.info("=" * 60)
                    self.logger.info(f"Planner Agent analyzing task (Round {i+1})")
                    self.logger.info("=" * 60)

                    original_format_kwargs = self.planner._prompt_format_kwargs.copy()
                    self.planner._prompt_format_kwargs.update({
                        'executor_result': results[f'executor_result_{i}']
                    })

                    planner_task = TaskInstance(
                        task_id=f"{task_id}_planner",
                        task_type="planner",
                        description=task_description,
                        input_data={},
                    )
                    
                    planner_trajectory = self.planner.run(planner_task)
                    self.planner._prompt_format_kwargs = original_format_kwargs
                    results[f'planner_trajectory_{i+1}'] = planner_trajectory
                    
                    # 提取planner Agent的回答
                    planner_result = self._extract_agent_response(planner_trajectory)
                    results[f'planner_result_{i+1}'] = planner_result

                    self.logger.info(f"Planner round_{i+1} completed")
                    self.logger.info(f"Planner result: {planner_result[:200]}...")

                    if "<task>" in planner_result:
                        search_target = planner_result.replace('<task>', '').replace('</task>', '').strip()
                    elif "<answer>" in planner_result:
                        final_answer = planner_result.replace('<answer>', '').replace('</answer>', '').strip()
                        results['final_answer'] = final_answer
                        break
                    else:
                        results['status'] = 'failed'
                        results['error'] = "Neither <task> nor <answer>"
                        
                        # 保存失败结果
                        result = {
                            "task_id": task_id,
                            "status": "failed",
                            "steps": 0,
                            "error": "Neither <task> nor <answer>",
                        }
                        self.results.append(result)
                        break
                        

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
    
    def _extract_agent_response(self, trajectory: Any) -> str:
        """从轨迹中提取Agent的最终回答

        Args:
            trajectory: 执行轨迹

        Returns:
            Agent的回答文本
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