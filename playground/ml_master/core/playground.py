""" ML-Master Playground：调用Draft/Debug/Improve 三个EXP"""
from __future__ import annotations

import logging
import threading
import time
from functools import partial
from pathlib import Path
from typing import Optional, Any
from datetime import datetime
from evomaster.core import BasePlayground, register_playground
from evomaster.agent import Agent

from .utils.grading import validate_submission
from .utils.uct import UCTSearchConfig, UCTDecayConfig, UCTSearchManager
from .utils.data_preview import generate as generate_data_preview
from .utils.playground_helpers import (
    append_trajectory,
    build_review,
    copy_submission,
    save_best,
    save_node_snapshot,
)
from .exp.draft_exp import DraftExp
from .exp.debug_exp import DebugExp
from .exp.improve_exp import ImproveExp

logger = logging.getLogger(__name__)


@register_playground("ml_master")
class MLMasterPlayground(BasePlayground):
    """ml-master 精简版：使用 BasePlayground Session/工具/Agent 创建"""

    def __init__(self, config_dir: Path | None = None, config_path: Path | None = None):
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "configs" / "ml_master"
        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.agents: dict[str, Agent] = {}
        self.trajectories: list[dict[str, Any]] = []
        session_config = self.config.session.get("local", {})
        parallel_config = session_config.get("parallel", {})
        if parallel_config.get("enabled", False):
            self.max_workers = int(parallel_config.get("max_parallel", 1))
        else:
            self.max_workers = 1

# --------------------------- 初始化 --------------------------- #
    def setup(self) -> None:
        self.logger.info("Setting up MLMasterPlayground using BasePlayground helpers...")

        llm_config_dict = self._setup_llm_config()
        self._llm_config_dict = llm_config_dict

        self._setup_session()
        self._setup_tools()

        agents_cfg = getattr(self.config, "agents", {})
        if not agents_cfg:
            raise ValueError("config.agents 未配置draft/debug/improve/metric")

        for name in ["draft", "debug", "improve", "metric"]:
            if name not in agents_cfg:
                raise ValueError(f"缺少 agent 配置: {name}")
            cfg = agents_cfg[name]
            enable_tools = cfg.get("enable_tools", False)
            agent = self._create_agent(
                name=name,
                agent_config=cfg,
                enable_tools=enable_tools,
                llm_config_dict=llm_config_dict,
            )
            self.agents[name] = agent
            self.logger.info("Agent created: %s", name)

        # 额外：baseline.json / grade.py 软链接
        self._ensure_prepared_links(Path(self.session.config.workspace_path))

    def cleanup(self) -> None:
        super().cleanup()

    def _ensure_prepared_links(self, workspace: Path) -> None:
        exp_id = getattr(self.config, "exp_id", None)
        data_root = getattr(self.config, "data_root", None)
        if not (exp_id and data_root):
            return

        prepared = Path(data_root) / exp_id / "prepared"
        src_base = prepared / "baseline.json"
        dst_base = workspace / "input" / "baseline.json"
        if src_base.exists():
            dst_base.parent.mkdir(parents=True, exist_ok=True)
            if dst_base.exists() or dst_base.is_symlink():
                dst_base.unlink()
            dst_base.symlink_to(src_base)

        src_grade = prepared / "grade.py"
        dst_grade = workspace / "grade.py"
        if src_grade.exists():
            if dst_grade.exists() or dst_grade.is_symlink():
                dst_grade.unlink()
            dst_grade.symlink_to(src_grade)

    def _resolve_worker_workspace(self, worker_index: int, main_workspace: Path) -> Path:
        session_config = self.config.session.get("local", {})
        parallel_config = session_config.get("parallel", {})
        split_workspace = parallel_config.get("split_workspace_for_exp", False)
        if split_workspace:
            return main_workspace / f"exp_{worker_index}"
        return main_workspace

    def _create_worker_agents(self, worker_index: int) -> dict[str, Agent]:
        return {
            "draft": self.copy_agent(self.agents["draft"], new_agent_name=f"draft_worker_{worker_index}"),
            "debug": self.copy_agent(self.agents["debug"], new_agent_name=f"debug_worker_{worker_index}"),
            "improve": self.copy_agent(self.agents["improve"], new_agent_name=f"improve_worker_{worker_index}"),
            "metric": self.copy_agent(self.agents["metric"], new_agent_name=f"metric_worker_{worker_index}"),
        }

    @staticmethod
    def _select_stage_and_inputs(target: Any) -> tuple[str, str, str]:
        if target.stage == "root":
            return "draft", "", ""
        if target.is_buggy or target.metric.value is None:
            return "debug", getattr(target, "code", ""), getattr(target, "stdout", "")
        return "improve", getattr(target, "code", ""), getattr(target, "stdout", "")

    def _run_one_node(
        self,
        *,
        worker_agents: dict[str, Agent],
        worker_workspace: Path,
        data_preview: str,
        task_description: str,
        stage: str,
        node: Any,
        prev_code: str,
        term_out: str,
        best_code: str | None,
        best_metric: float | None,
        memory: str,
        exp_index: int,
    ) -> dict[str, Any]:
        if stage == "draft":
            exp = DraftExp(
                worker_agents["draft"],
                worker_agents["metric"],
                self.session,
                worker_workspace,
                getattr(self.config, "exp_id", None),
                data_preview,
                node,
                exp_index=exp_index,
            )
            return exp.run(task_description, memory=memory)
        if stage == "debug":
            exp = DebugExp(
                worker_agents["debug"],
                worker_agents["metric"],
                self.session,
                worker_workspace,
                getattr(self.config, "exp_id", None),
                data_preview,
                node,
                exp_index=exp_index,
            )
            return exp.run(task_description, prev_code=prev_code, term_out=term_out, issue="")
        exp = ImproveExp(
            worker_agents["improve"],
            worker_agents["metric"],
            self.session,
            worker_workspace,
            getattr(self.config, "exp_id", None),
            data_preview,
            node,
            exp_index=exp_index,
        )
        return exp.run(
            task_description,
            best_code=best_code or prev_code,
            best_metric=best_metric,
            memory=memory,
            term_out=term_out,
        )

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        try:
            self.setup()
            self._setup_trajectory_file(output_file)
            workspace = Path(self.session.config.workspace_path)
            (workspace / "working").mkdir(parents=True, exist_ok=True)
            (workspace / "best_solution").mkdir(parents=True, exist_ok=True)
            (workspace / "best_submission").mkdir(parents=True, exist_ok=True)
            submission_dir = workspace / "submission"
            submission_dir.mkdir(parents=True, exist_ok=True)

            servers = getattr(self.config, "grading_servers", []) or []
            search_cfg = UCTSearchConfig()
            search_mgr = UCTSearchManager(
                search_cfg=search_cfg,
                decay_cfg=UCTDecayConfig(),
                grader=lambda exp_id, p: validate_submission(
                    exp_id,
                    p,
                    server_urls=servers,
                    dataset_root=getattr(self.config, "data_root", None),
                ),
                exp_id=getattr(self.config, "exp_id", "unknown"),
                submission_dir=submission_dir,
            )
            search_mgr.set_snapshot_fn(
                lambda node, sub, review, reward: save_node_snapshot(
                    self.run_dir,
                    Path(self.session.config.workspace_path),
                    node,
                    sub,
                    review,
                    reward,
                    search_mgr,
                )
            )

            results: dict = {"status": "completed", "draft": [], "debug": [], "improve": []}
            best_state: dict[str, Optional[Any]] = {
                "code": None,
                "metric": None,
                "node_id": None,
                "dispatch_id": 0,
                "active_jobs": 0,
            }
            max_steps = 40
            state_lock = threading.Lock()
            worker_agents_map = {i: self._create_worker_agents(i) for i in range(self.max_workers)}

            def worker_loop(worker_index: int) -> dict[str, Any]:
                worker_agents = worker_agents_map[worker_index]
                worker_workspace = self._resolve_worker_workspace(worker_index, workspace)
                worker_workspace.mkdir(parents=True, exist_ok=True)
                self._ensure_prepared_links(worker_workspace)
                (worker_workspace / "working").mkdir(parents=True, exist_ok=True)
                (worker_workspace / "submission").mkdir(parents=True, exist_ok=True)
                worker_submission_dir = worker_workspace / "submission"
                data_preview = generate_data_preview(worker_workspace)
                completed = 0

                while True:
                    should_wait = False
                    with state_lock:
                        if search_mgr.current_step >= max_steps:
                            break
                        target = search_mgr.select_next()
                        if target is None:
                            if int(best_state["active_jobs"] or 0) > 0:
                                should_wait = True
                            else:
                                break
                        elif target.stage != "root" and target.is_buggy is None:
                            # Target node has not been evaluated yet; wait for running jobs.
                            should_wait = True

                        if should_wait:
                            pass
                        else:
                            stage, prev_code, term_out = self._select_stage_and_inputs(target)
                            node = search_mgr.create_child(target, stage=stage, plan="", code="")
                            best_state["active_jobs"] = int(best_state["active_jobs"] or 0) + 1
                            dispatch_id = int(best_state["dispatch_id"] or 0)
                            best_state["dispatch_id"] = dispatch_id + 1
                            memory = (
                                search_mgr.root.fetch_child_memory()
                                if stage == "draft"
                                else target.fetch_child_memory()
                            )
                            best_code = best_state["code"]
                            best_metric = best_state["metric"]
                    if should_wait:
                        time.sleep(0.1)
                        continue

                    try:
                        res = self._run_one_node(
                            worker_agents=worker_agents,
                            worker_workspace=worker_workspace,
                            data_preview=data_preview,
                            task_description=task_description,
                            stage=stage,
                            node=node,
                            prev_code=prev_code,
                            term_out=term_out,
                            best_code=best_code,
                            best_metric=best_metric,
                            memory=memory,
                            exp_index=dispatch_id,
                        )
                    except Exception as exc:  # pragma: no cover - defensive fallback
                        self.logger.error("Worker %s failed on node %s: %s", worker_index, node.id, exc, exc_info=True)
                        res = {
                            "plan": "",
                            "code": "",
                            "raw_response": str(exc),
                            "exec": {"stdout": str(exc), "exit_code": -1},
                            "metric": None,
                            "metric_detail": {"is_bug": True, "has_submission": False},
                        }

                    with state_lock:
                        best_state["active_jobs"] = max(int(best_state["active_jobs"] or 0) - 1, 0)
                        node.code = res.get("code", "")
                        node.plan = res.get("plan", "")
                        node.stdout = res.get("exec", {}).get("stdout", "")
                        node.exit_code = res.get("exec", {}).get("exit_code", None)

                        copied = copy_submission(
                            submission_dir,
                            node.id,
                            source_submission_dir=worker_submission_dir,
                        )
                        review = build_review(res, has_submission=copied is not None)
                        reward = search_mgr.ingest_result(node, review)
                        save_node_snapshot(
                            self.run_dir,
                            Path(self.session.config.workspace_path),
                            node,
                            copied,
                            review,
                            reward,
                            search_mgr,
                        )

                        trail = {
                            "ts": datetime.utcnow().isoformat(),
                            "step": search_mgr.current_step,
                            "stage": stage,
                            "node_id": node.id,
                            "parent": getattr(node.parent, "id", None),
                            "is_buggy": node.is_buggy,
                            "metric": getattr(node.metric, "value", None),
                            "has_submission": copied is not None,
                            "submission_file": str(copied) if copied else None,
                            "worker_index": worker_index,
                        }
                        append_trajectory(self, trail, logger=self.logger)
                        results[stage].append(res)

                        if (
                            search_mgr.best_node
                            and search_mgr.best_node.id != best_state["node_id"]
                            and search_mgr.best_node.metric.value is not None
                        ):
                            best_state["node_id"] = search_mgr.best_node.id
                            best_state["metric"] = search_mgr.best_node.metric.value
                            best_state["code"] = search_mgr.best_node.code
                            best_sub = submission_dir / f"submission_{best_state['node_id']}.csv"
                            save_best(
                                self.logger,
                                workspace,
                                str(best_state["code"] or ""),
                                best_sub if best_sub.exists() else copied,
                            )
                    completed += 1

                return {"worker_index": worker_index, "completed": completed}

            worker_tasks = [partial(worker_loop, i) for i in range(self.max_workers)]
            worker_results = self.execute_parallel_tasks(worker_tasks, max_workers=self.max_workers)
            for idx, wr in enumerate(worker_results):
                if isinstance(wr, Exception):
                    self.logger.error("Worker %s returned exception: %s", idx, wr)
                else:
                    self.logger.info("Worker summary: %s", wr)

            return results
        finally:
            self.cleanup()


