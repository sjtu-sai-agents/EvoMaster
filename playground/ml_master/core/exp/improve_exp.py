"""Improve Experiment Implementation."""
import logging
from pathlib import Path

from evomaster.agent import BaseAgent
from evomaster.utils.types import TaskInstance

from . import NodeExp
from ..utils.runtime import (
    extract_agent_response,
    extract_python_code,
    extract_text_up_to_code,
    run_code_via_bash,
)

logger = logging.getLogger(__name__)


class ImproveExp(NodeExp):
    """Improve 实验：在已有最佳方案上做原子改进"""

    def __init__(self, agent, metric_agent, session, workspace: Path, exp_id: str | None, data_preview: str, node, exp_index: int = 0):
        super().__init__(agent, metric_agent, session, workspace, exp_id, data_preview, node, exp_index)

    def run(
        self,
        task_description: str,
        best_code: str,
        best_metric: float | None,
        memory: str,
        term_out: str,
    ) -> dict:
        node_id = self.node.id
        BaseAgent.set_exp_info(exp_name=f"improve_{node_id[:8]}", exp_index=self.exp_index)
        fmt = {
            "task_description": task_description,
            "best_code": best_code,
            "best_metric": best_metric,
            "memory": memory,
            "execution_output": term_out,
            "data_preview": self.data_preview,
            "SUBMISSION_FILE": str(self.workspace / "submission" / "submission.csv"),
            "SERVER_URL": "http://localhost:5003/validate",
        }
        orig_fmt = self.agent._prompt_format_kwargs.copy()
        self.agent._prompt_format_kwargs.update(fmt)
        try:
            task = TaskInstance(task_id=f"{node_id}_improve", task_type="improve", description=task_description, input_data={})
            traj = self.agent.run(task)
            text = extract_agent_response(traj)
        finally:
            self.agent._prompt_format_kwargs = orig_fmt

        plan = extract_text_up_to_code(text)
        code = extract_python_code(text)
        exec_res = run_code_via_bash(self.agent, self.workspace, code, node_id)
        metric_info = self._run_metric_agent(code, exec_res.get("stdout", ""))

        return {
            "plan": plan,
            "code": code,
            "raw_response": text,
            "exec": exec_res,
            "metric": metric_info.get("metric"),
            "metric_detail": metric_info,
        }
