"""Minimal Skill Task Playground：Analyze → Plan → Search → Summarize 四 Agent 流程"""

import logging
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground

from .utils.rag_utils import get_db_from_description, resolve_db_to_absolute_paths, set_embedding_config
from .exp import AnalyzeExp, SearchExp, SummarizeExp


@register_playground("minimal_skill_task")
class MinimalSkillTaskPlayground(BasePlayground):
    def __init__(self, config_dir: Path = None, config_path: Path = None):
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "agent" / "minimal_skill_task"
        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.agents.declare("analyze_agent", "plan_agent", "search_agent", "summarize_agent")# make sure these name are available in the config yaml



    def _setup_embedding(self) -> None:
        config_dict = self.config.model_dump() if hasattr(self.config, "model_dump") else {}
        embedding_config = config_dict.get("embedding", {}) or {}
        if not embedding_config:
            return

        set_embedding_config(embedding_config)
        emb_type = embedding_config.get("type", "local")
        self.logger.info(f"Embedding configured: type={emb_type}")

        if emb_type != "openai":
            return

        openai_cfg = embedding_config.get("openai", {}) or {}
        model = openai_cfg.get("model", "text-embedding-3-large")
        base_url = openai_cfg.get("base_url", "")
        api_key = openai_cfg.get("api_key", "")

        # 注入到环境变量，供 rag/scripts/search.py 读取
        if api_key:
            os.environ["OPENAI_EMBEDDING_API_KEY"] = api_key
        if base_url:
            os.environ["OPENAI_EMBEDDING_BASE_URL"] = base_url

        # 日志只打印非敏感信息
        self.logger.info(f"  OpenAI embedding model: {model}")
        if base_url:
            self.logger.info(f"  OpenAI embedding base_url: {base_url}")



    def setup(self) -> None:
        self.logger.info("Setting up minimal skill task playground...")

        self._setup_embedding()


        self._setup_session()
        self._setup_agents()

        self.logger.info("Minimal skill task playground setup complete")

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        try:
            self.setup()

            self._setup_trajectory_file(output_file)

            db = get_db_from_description(task_description)
            db = resolve_db_to_absolute_paths(db)  # vec_dir、nodes_data、model 转为绝对路径
            task_id = getattr(self, "task_id", "task_0")


            self.logger.info("===========================AnalyzeExp===========================")
            analyze_exp = AnalyzeExp(self.agents.analyze_agent, self.config)
            analyze_output, analyze_traj = analyze_exp.run(task_description, db, task_id=task_id)

            self.logger.info("===========================SearchExp (Plan + Search, 2 rounds)===========================")
            search_exp = SearchExp(self.agents.plan_agent, self.agents.search_agent, self.config)
            search_results, search_trajs = search_exp.run(task_description, analyze_output, db, task_id=task_id)

            self.logger.info("===========================SummarizeExp===========================")
            summarize_exp = SummarizeExp(self.agents.summarize_agent, self.config)
            summarize_output, summarize_traj = summarize_exp.run(
                task_description, search_results, db, task_id=task_id
            )

            total_steps = (
                len(getattr(analyze_traj, "steps", []))
                + sum(len(getattr(t, "steps", [])) for t in search_trajs)
                + len(getattr(summarize_traj, "steps", []))
            )

            result = {
                "status": "completed",
                "steps": total_steps,
                "analyze_output": analyze_output,
                "search_results": search_results,
                "summarize_output": summarize_output,
            }
            return result

        except Exception as e:
            self.logger.error(f"Minimal skill task failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "steps": 0,
                "error": str(e),
            }
        finally:
            self.cleanup()
