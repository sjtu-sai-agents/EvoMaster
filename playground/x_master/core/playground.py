"""X-Master Playground 实现

实现完整的X-Master工作流：
1. Solver: 生成初始解决方案
2. Critic: 批评和修正解决方案
3. Rewriter: 重写和整合解决方案
4. Selector: 选择最佳解决方案

"""

import logging
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# 确保可以导入evomaster模块
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground
from evomaster import TaskInstance

from .exp import SolveExp, CritiqueExp, RewriteExp, SelectExp

@register_playground("x_master")
class XMasterPlayground(BasePlayground):
    """X-Master Playground
    
    协调四个Exp类，实现完整的X-Master工作流。
    """
    
    def __init__(self, config_dir: Path = None, config_path: Path = None):
        """初始化X-Master Playground
        
        Args:
            config_dir: 配置目录路径，默认为 configs/xmaster/
            config_path: 配置文件完整路径
        """
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "agent" / "x_master"
        
        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 存储四个组件的Agent
        self.solver_agent = None
        self.critic_agent = None
        self.rewriter_agent = None
        self.selector_agent = None
        
        # 存储Exp实例
        self.solver_exp = None
        self.critic_exp = None
        self.rewriter_exp = None
        self.selector_exp = None
        
        # 存储中间结果
        self.solver_results = []
        self.critic_results = []
        self.rewriter_results = []
        self.selector_results = []
        
    
    def setup(self) -> None:
        """初始化所有组件
        
        创建四个Agent和对应的Exp实例。
        """
        self.logger.info("Setting up X-Master playground...")
        
        # 1. 准备 LLM 配置
        llm_config = self._setup_llm_config()
        self._llm_config = llm_config
        
        # 2. 创建 Session（所有Agent共享）
        self._setup_session()
        
        # 3. 创建工具注册表
        self._setup_tools()

        # 4. 从配置中获取工作流参数
        self._load_workflow_config()

        # 5. 创建四个组件的Agent
        self._setup_agents(llm_config)


        self.logger.info("X-Master playground setup complete")
    
    def _load_workflow_config(self) -> None:
        """从配置中加载工作流参数

        TODO: 并行执行暂未实现，agent_num 和 max_workers 配置当前不生效。
        """
        xmaster_config = getattr(self.config, 'xmaster', {})
        if not xmaster_config:
            xmaster_config = {}

        self.agent_num = xmaster_config.get('agent_num', 1)
        self.max_workers = xmaster_config.get('max_workers', 1)
        self.parallel = xmaster_config.get('parallel', True)

        self.logger.info(f"Workflow config: agent_num={self.agent_num}, max_workers={self.max_workers}")
    
    def _setup_agents(self, llm_config: Dict[str, Any]) -> None:
        """创建四个组件的Agent
        
        Args:
            llm_config: LLM配置字典
        """
        agents_config = getattr(self.config, 'agents', {})
        if not agents_config:
            raise ValueError(
                "No agents configuration found. "
                "Please add 'agents' section to config.yaml"
            )

        # 1. 创建Solver Agent
        if 'Solver' in agents_config:
            solver_config = agents_config['Solver']
            self.solver_agent = self._create_agent(
                name="Solver",
                agent_config=solver_config,
                llm_config=llm_config,
            )
            self.logger.info("Solver Agent created")

        # 2. 创建Critic Agent
        if 'Critic' in agents_config:
            critic_config = agents_config['Critic']
            self.critic_agent = self._create_agent(
                name="Critic",
                agent_config=critic_config,
                llm_config=llm_config,
            )
        self.logger.info("Critic Agent created")

        # 3. 创建Rewriter Agent
        if 'Rewriter' in agents_config:
            rewriter_config = agents_config['Rewriter']
            self.rewriter_agent = self._create_agent(
                name="Rewriter",
                agent_config=rewriter_config,
                llm_config=llm_config,
            )
        self.logger.info("Rewriter Agent created")

        # 4. 创建Selector Agent
        if 'Selector' in agents_config:
            selector_config = agents_config['Selector']
            self.selector_agent = self._create_agent(
                name="Selector",
                agent_config=selector_config,
                llm_config=llm_config,
            )
            self.logger.info("Selector Agent created")


    def _create_exp(self, exp_index, exp_name:str):
        """创建多智能体实验实例"""
        exp = None
        
        if exp_name == "solve":
            solver_agent_copy = self.copy_agent(
                self.solver_agent, 
                new_agent_name=f"solve_exp_{exp_index}"
            ) if self.solver_agent else None
            exp = SolveExp(
                solver_agent=solver_agent_copy,
                config=self.config,
                index=exp_index
            )
        
        elif exp_name == "critique":
            critic_agent_copy = self.copy_agent(
                self.critic_agent, 
                new_agent_name=f"critique_exp_{exp_index}"
            ) if self.critic_agent else None
            exp = CritiqueExp(
                critic_agent=critic_agent_copy,
                config=self.config,
                index=exp_index
            )
        
        elif exp_name == "rewrite":
            rewriter_agent_copy = self.copy_agent(
                self.rewriter_agent, 
                new_agent_name=f"rewrite_exp_{exp_index}"
            ) if self.rewriter_agent else None
            exp = RewriteExp(
                rewriter_agent=rewriter_agent_copy,
                config=self.config,
                index=exp_index
            )
        
        elif exp_name == "select":
            selector_agent_copy = self.copy_agent(
                self.selector_agent, 
                new_agent_name=f"select_exp_{exp_index}"
            ) if self.selector_agent else None
            exp = SelectExp(  
                selector_agent=selector_agent_copy,
                config=self.config,
                index=exp_index
            )
        
        else:
            raise ValueError(f"Unknown exp_name: {exp_name}. Expected one of: solve, critique, rewrite, select")
        
        if exp is None:
            raise RuntimeError(f"Failed to create exp: {exp_name}")
        
        return exp
    
    def _extract_solutions_from_results(self, results: List) -> List[str]:
        """从Exp结果中提取解决方案列表"""
        solutions = []
        #直接查找 solutions_result_{i}
        for result in results:
            index = result['exp_index']
            key = f"solver_result"
            if key in result and result[key] is not None:
                solutions.append(result[key])
                self.logger.info(f"index:{index} 找到 {key}: {result[key][:50]}...")
            elif key in result:
                self.logger.warning(f"index:{index} {key} 的值为 None，跳过")
        self.logger.info(f"最终提取到 {len(solutions)} 个解决方案")
        return solutions
    
    def _extract_corrected_solutions(self, results: List) -> List[str]:
        """从Critic结果中提取修正后的解决方案
        
        Args:
            results: CritiqueExp运行结果
            
        Returns:
            修正后的解决方案列表
        """
        solutions = []
        #直接查找 critic_result_{i}
        for result in results:
            index = result['exp_index']
            key = f"critic_result"
            if key in result and result[key] is not None:
                solutions.append(result[key])
                self.logger.info(f"index:{index} 找到 {key}: {result[key][:50]}...")
            elif key in result:
                self.logger.warning(f"index:{index} {key} 的值为 None，跳过")
        self.logger.info(f"最终提取到 {len(solutions)} 个解决方案")
        return solutions

    def _extract_rewritten_solutions(self, results: List) -> List[str]:
        """从Rewriter结果中提取重写后的解决方案
        
        Args:
            results: RewriteExp运行结果
            
        Returns:
            重写后的解决方案列表
        """
        solutions = []
        #直接查找 rewriter_result_{i}
        for result in results:
            index = result['exp_index']
            key = f"rewriter_result"
            if key in result and result[key] is not None:
                solutions.append(result[key])
                self.logger.info(f"index:{index} 找到 {key}: {result[key][:50]}...")
            elif key in result:
                self.logger.warning(f"index:{index} {key} 的值为 None，跳过")
        self.logger.info(f"最终提取到 {len(solutions)} 个解决方案")
        return solutions
    
    def _extract_selected_solution(self, results: Dict[str, Any]) -> str:
        """从Selector结果中提取选中的解决方案
        
        Args:
            results: SelectExp运行结果
            
        Returns:
            选中的解决方案
        """
        key = f"selector_result"
        solutions = results[key]
        self.logger.info(f"找到 {key}: {results[key][:50]}...")
        return solutions
    
    def _run_with_parallel(self,task_description: str, task_id: str = None):
        self.logger.info(f"=== Parallel Process ({self.agent_num} agents) ===")
        from functools import partial
        # ---------- Phase 1: Solver (并行) ----------
        self.logger.info(f"=== Phase 1: Solver (parallel, {self.agent_num} agents) ===")
        solver_tasks = []
        for i in range(self.agent_num):
            exp = self._create_exp(exp_index=i, exp_name="solve")
            task_func = partial(
                exp.run,
                task_description=task_description,
                task_id=f"{task_id}_solver",
            )
            solver_tasks.append(task_func)
        
        solver_results_list = self.execute_parallel_tasks(solver_tasks, max_workers=self.max_workers)

        self.solver_results = solver_results_list

        original_solutions = self._extract_solutions_from_results(self.solver_results)

        self.logger.info(f"Solver generated {len(original_solutions)} solutions")


        # ---------- Phase 2: Critic (并行，一一对应) ----------
        self.logger.info(f"=== Phase 2: Critic (parallel, {self.agent_num} agents) ===")
        critic_tasks = []
        for i in range(self.agent_num):
            exp = self._create_exp(exp_index=i, exp_name="critique")
            task_func = partial(
                exp.run,
                task_description=task_description,
                solution=original_solutions[i],   # 只传递对应的一个解
                task_id=f"{task_id}_critic"
            )
            critic_tasks.append(task_func)
        
        critic_results_list = self.execute_parallel_tasks(critic_tasks, max_workers=self.max_workers)

        self.critic_results = critic_results_list

        corrected_solutions = self._extract_corrected_solutions(self.critic_results)
        self.logger.info(f"Critic generated {len(corrected_solutions)} corrected solutions")

        # ---------- Phase 3: Rewriter (并行，综合所有) ----------
        self.logger.info(f"=== Phase 3: Rewriter (parallel, {self.agent_num} agents) ===")
        rewriter_tasks = []
        for i in range(self.agent_num):
            exp = self._create_exp(exp_index=i, exp_name="rewrite")
            task_func = partial(
                exp.run,
                task_description=task_description,
                solutions=corrected_solutions,       # 传递所有修正解
                task_id=f"{task_id}_rewriter"
            )
            rewriter_tasks.append(task_func)
        
        rewriter_results_list = self.execute_parallel_tasks(rewriter_tasks, max_workers=self.max_workers)

        self.rewriter_results = rewriter_results_list

        rewritten_solutions = self._extract_rewritten_solutions(self.rewriter_results)
        
        self.logger.info(f"Rewriter generated {len(rewritten_solutions)} rewritten solutions")

        # ---------- Phase 4: Selector (单 Agent) ----------
        self.logger.info("=== Phase 4: Selector ===")
        selector_exp = self._create_exp(exp_index=0, exp_name="select")
        self.selector_results = selector_exp.run(
            task_description=task_description,
            solutions=rewritten_solutions,
            task_id=f"{task_id}_selector"
        )

        selected_solution = self._extract_selected_solution(self.selector_results)
        self.logger.info("Selector completed, best solution selected")

        return original_solutions, corrected_solutions, rewritten_solutions, selected_solution


    def _run_with_serial(self,task_description: str, task_id: str = None):

        self.logger.info(f"=== Serial Process ({self.agent_num} agents) ===")
        # 1. Solver阶段：生成初始解决方案
        self.logger.info(f"=== Phase 1: Solver (serial, {self.agent_num} agents) ===")
        for i in range(self.agent_num):
            exp = self._create_exp(exp_index=i,exp_name="solve")
            solver_results = exp.run(
                task_description=task_description,
                task_id=f"{task_id}_solver"
            )
            self.solver_results.append(solver_results)

        # 提取Solver的解决方案
        original_solutions = self._extract_solutions_from_results(self.solver_results)
        self.logger.info(f"Solver generated {len(original_solutions)} solutions")
        
        # 2. Critic阶段：批评和修正解决方案
        self.logger.info(f"=== Phase 2: Critic (serial, {self.agent_num} agents) ===")
        for i in range(self.agent_num):
            exp = self._create_exp(exp_index=i,exp_name="critique")
            critic_results = exp.run(
                task_description=task_description,
                solution=original_solutions[i],  
                task_id=f"{task_id}_critic"
            )
            self.critic_results.append(critic_results)
        
        # 提取Critic修正后的解决方案
        corrected_solutions = self._extract_corrected_solutions(self.critic_results)
        self.logger.info(f"Critic generated {len(corrected_solutions)} corrected solutions")
        
        # 3. Rewriter阶段：重写和整合解决方案
        self.logger.info(f"=== Phase 3: Rewriter (serial, {self.agent_num} agents) ===")
        
        # 准备Rewriter的输入数据

        for i in range(self.agent_num):
            exp = self._create_exp(exp_index=i,exp_name="rewrite")
            rewriter_results = exp.run(
                task_description=task_description,
                solutions=corrected_solutions,
                task_id=f"{task_id}_rewriter"
            )
            self.rewriter_results.append(rewriter_results)
        
        # 提取Rewriter重写后的解决方案
        rewritten_solutions = self._extract_rewritten_solutions(self.rewriter_results)
        self.logger.info(f"Rewriter generated {len(rewritten_solutions)} rewritten solutions")
        
        # 4. Selector阶段：选择最佳解决方案
        self.logger.info("=== Phase 4: Selector ===")
        
        # 准备Selector的输入数据
        exp = self._create_exp(exp_index=i,exp_name="select")

        self.selector_results = exp.run(
            task_description=task_description,
            solutions=rewritten_solutions,
            task_id=f"{task_id}_selector"
        )
        
        # 提取Selector选中的解决方案
        selected_solution = self._extract_selected_solution(self.selector_results)
        self.logger.info("Selector completed, best solution selected")
        

        return original_solutions, corrected_solutions, rewritten_solutions, selected_solution
    
    def run_xmaster_workflow(self, task_description: str, task_id: str = None) -> Dict[str, Any]:
        """运行完整的X-Master工作流
        
        Args:
            task_description: 任务描述
            task_id: 任务ID（用于批量处理）
            
        Returns:
            完整的X-Master工作流结果
        """
        if not task_id:
            task_id = "xmaster_task_001"
        
        self.logger.info(f"Starting X-Master workflow for task: {task_id}")
        self.logger.info(f"Task description: {task_description[:100]}...")
        
        # 是否并行处理
        if self.parallel:
            original_solutions, corrected_solutions, rewritten_solutions, selected_solution = self._run_with_parallel(task_description, task_id)
        else:
            original_solutions, corrected_solutions, rewritten_solutions, selected_solution = self._run_with_serial(task_description, task_id)

        
        # 构建最终结果
        final_result = {
            "status": "completed",
            "task_id": task_id,
            "task_description": task_description,
            "final_solution": selected_solution,
            "phase_results": {
                "solver": original_solutions,
                "critic": corrected_solutions,
                "rewriter": rewritten_solutions,
                "selector": selected_solution
            },
            "solutions_summary": {
                "original_count": len(original_solutions),
                "corrected_count": len(corrected_solutions),
                "rewritten_count": len(rewritten_solutions)
            },
            "trajectory": {
                "solver_trajectory":self.solver_results,
                "critic_trajectory":self.critic_results,
                "rewriter_trajectory":self.rewriter_results,
                "selector_trajectory":self.selector_results
            }
        }
        
        self.logger.info("X-Master workflow completed successfully")
        
        return final_result
    
    def run(self, task_description: str, output_file: str | None = None) -> Dict[str, Any]:
        """运行X-Master工作流（覆盖基类方法）

        Args:
            task_description: 任务描述
            output_file: 结果保存文件

        Returns:
            运行结果
        """
        try:
            self.setup()

            # 设置 trajectory 文件路径（使用基类方法，统一目录结构）
            self._setup_trajectory_file(output_file)

            # 运行完整的X-Master工作流
            task_id = getattr(self, 'task_id', None)
            final_result = self.run_xmaster_workflow(task_description, task_id)

            return final_result

        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """清理资源
        
        覆盖基类方法，清理所有Agent和Exp。
        """
        # 清理基类资源
        super().cleanup()
        
        # 清空Agent引用
        self.solver_agent = None
        self.critic_agent = None
        self.rewriter_agent = None
        self.selector_agent = None
        
        
        # 清空结果
        self.solver_results = None
        self.critic_results = None
        self.rewriter_results = None
        self.selector_results = None
        
        self.logger.debug("X-Master resources cleaned up")
    
    