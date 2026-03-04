
# coding: utf-8
"""Exp 基础类与导出。辅助工具已拆分utils包中
"""

import logging
from pathlib import Path
from evomaster.core.exp import BaseExp
from evomaster.utils.types import TaskInstance

from ..utils.runtime import extract_agent_response
from ..utils.metric import parse_metric_content

logger = logging.getLogger(__name__)


class NodeExp(BaseExp):
    """针对单个UCT节点的基础Exp，统一持有节点与数据预览信息，便于后续复用"""

    def __init__(self, agent, metric_agent, session, workspace: Path, exp_id: str | None, data_preview: str, node, exp_index: int = 0):
        super().__init__(agent=agent, config=None)
        self.metric_agent = metric_agent
        self.session = session
        self.workspace = workspace
        self.exp_id = exp_id
        self.data_preview = data_preview
        self.node = node
        self.exp_index = exp_index

    def _run_metric_agent(self, code: str, stdout: str) -> dict:
        if not self.metric_agent:
            return {"metric": None, "is_bug": True, "has_submission": False}

        orig_fmt = self.metric_agent._prompt_format_kwargs.copy()
        self.metric_agent._prompt_format_kwargs.update({"code": code, "stdout": stdout})
        try:
            task = TaskInstance(task_id="parse_metric", task_type="metric", description="parse metric", input_data={})
            traj = self.metric_agent.run(task)
            resp = extract_agent_response(traj)
            return parse_metric_content(resp)
        finally:
            self.metric_agent._prompt_format_kwargs = orig_fmt


__all__ = ["NodeExp"]

