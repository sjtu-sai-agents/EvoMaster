import os
import logging
import sys
from pathlib import Path
import shutil
import copy
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import BasePlayground, register_playground
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evomaster.agent import Agent


from evomaster.utils.types import TaskInstance
from .exp.draft_exp import DraftExp
from .exp.research_exp import ResearchExp
from .exp.improve_exp import ImproveExp
from .utils.data_preview import generate
from .utils.code import save_code_to_file

@register_playground("minimal_kaggle")
class MinimalKagglePlayground(BasePlayground):
    def __init__(self, config_dir: Path = None, config_path: Path = None):
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "agent" / "minimal_kaggle"
        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.agents.declare("draft_agent", "debug_agent", "improve_agent", "reseach_agent", "knowledge_promotion_agent", "metric_agent")

        self.best_score = None
        self.best_solution = None
        self.knowledge = "There is no memory now."
        
        self.is_lower_better = False
        self.mcp_manager = None

        self.exp_index = 0 # for trajectory visualizing

    def setup(self) -> None:
        self.logger.info("Setting up minimal kaggle playground...")

        self._setup_session()
        self._setup_agents()

        self.logger.info("Minimal kaggle playground setup complete")

    def compare_score(self, old_score, new_score):
        if old_score is None or new_score is None:
            return True if new_score is not None else False
        if old_score < new_score and self.is_lower_better == False:
            return True
        elif old_score > new_score and self.is_lower_better == True:
            return True
        else:
            return False

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        try:
            self.setup()

            self._setup_trajectory_file(output_file)

            data_knowledge = "NO DATA KNOWLEDGE this time"
            model_knowledge = "NO MODEL KNOWLEDGE this time"
            self.logger.info(f"working_dir: {self.agents.draft_agent.session.config.workspace_path}")
            os.makedirs(os.path.join(self.agents.draft_agent.session.config.workspace_path, "best_submission"), exist_ok=True)
            os.makedirs(os.path.join(self.agents.draft_agent.session.config.workspace_path, "best_solution"), exist_ok=True)
            os.makedirs(os.path.join(self.agents.draft_agent.session.config.workspace_path, "submission"), exist_ok=True)
            os.makedirs(os.path.join(self.agents.draft_agent.session.config.workspace_path, "working"), exist_ok=True)
            data_preview = generate(self.agents.draft_agent.session.config.workspace_path)
            self.logger.info(f"Data preview: {data_preview}")
            self.logger.info("Running experiment...")
            draft_exp = DraftExp(self.agents.draft_agent, self.agents.debug_agent, self.agents.metric_agent, self.config,self.exp_index)
            self.exp_index += 1
            is_sucess, validation_score, uid,self.best_solution = draft_exp.run(task_description, data_preview, data_knowledge, model_knowledge)
            if is_sucess:
                shutil.copy(os.path.join(self.agents.draft_agent.session.config.workspace_path, "submission", f"submission_{uid}.csv"), os.path.join(self.agents.draft_agent.session.config.workspace_path, "best_submission", f"submission.csv"))
                save_code_to_file(os.path.join(self.agents.draft_agent.session.config.workspace_path, "best_solution"), "best_solution.py", self.best_solution)
            for reseach_round in range(10):
                research_exp = ResearchExp(self.agents.reseach_agent, self.config,self.exp_index)
                self.exp_index += 1
                research_plan = research_exp.run(task_description, data_preview, self.best_solution,self.knowledge)
                for direction in research_plan:
                    direction_best_solution = self.best_solution
                    direction_best_score = self.best_score
                    ideas = list(research_plan[direction].items())
                    for idea in ideas:
                        improve_exp = ImproveExp(self.agents.improve_agent, self.agents.debug_agent, self.agents.metric_agent, self.config,self.exp_index)
                        self.exp_index += 1
                        is_sucess, validation_score, uid,self.best_solution = improve_exp.run(task_description, data_preview, direction_best_solution, idea)
                        if self.compare_score(direction_best_score, validation_score):
                            direction_best_score = validation_score
                            direction_best_solution = self.best_solution
                            shutil.copy(os.path.join(self.agents.improve_agent.session.config.workspace_path, "submission", f"submission_{uid}.csv"), os.path.join(self.agents.draft_agent.session.config.workspace_path, "best_submission", f"submission.csv"))
                            save_code_to_file(os.path.join(self.agents.improve_agent.session.config.workspace_path, "best_solution"), "best_solution.py", self.best_solution)
                    
                    self.best_solution = direction_best_solution
                    self.best_score = direction_best_score

            result = {
                "status": "completed",
                "steps": 0,
            }
            return result
        except Exception as e:
            self.logger.error(f"Minimal Kaggle task execution failed: {e}", exc_info=True)
            result = {
                "status": "failed",
                "steps": 0,
                "error": str(e),
            }
            return result

        finally:
            self.cleanup()

