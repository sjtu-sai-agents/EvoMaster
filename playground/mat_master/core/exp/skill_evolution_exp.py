"""SkillEvolutionExp: evolution layer (mode='skill_evolution').

When the agent lacks a tool: code -> sandbox test -> register via
MatMasterSkillRegistry. Uses run_dir for workspace when set.
"""

import logging
from pathlib import Path

from evomaster.core.exp import BaseExp
from evomaster.utils.types import TaskInstance


def _get_mat_master_config(config) -> dict:
    try:
        if hasattr(config, "model_dump"):
            d = config.model_dump()
        else:
            d = dict(config) if config else {}
        return d.get("mat_master") or {}
    except Exception:
        return {}


class SkillEvolutionExp(BaseExp):
    """Skill evolution mode: evolution layer.

    When the main task needs a capability that does not exist, this Exp
    guides the agent to write a new Skill (Python script + SKILL.md),
    tests it in a sandbox, then registers it via MatMasterSkillRegistry.
    """

    def __init__(self, agent, config):
        super().__init__(agent, config)
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self, task_description: str, task_id: str = "evo_task") -> dict:
        """Evolve a new skill for the given requirement (task_description)."""
        self.logger.info("[Evo] Attempting to evolve skill for: %s", task_description[:80])

        prompt = (
            f"I need a new tool to handle this requirement: {task_description}\n"
            "Please write a Python script and a SKILL.md following EvoMaster standards.\n"
            "The script should be standalone and testable.\n\n"
            "Requirements:\n"
            "1. Output directory must be exactly: new_skill (create new_skill/ and new_skill/scripts/ as needed). Do not use names like new_skill_2.\n"
            "2. Write all file contents with the str_replace_editor tool (command=create, path=<absolute path>, file_text=<content>). Use the current working directory shown above as the base; e.g. <working_dir>/new_skill/SKILL.md and <working_dir>/new_skill/scripts/<script>.py. Do not use bash (cat, echo, here-docs) or Python one-liners to write long file content—on Windows these often fail or write to the wrong place.\n"
            "3. Create new_skill/SKILL.md (with YAML frontmatter: name, description) and new_skill/scripts/<your_script>.py with full, runnable code."
        )
        task = TaskInstance(task_id=f"{task_id}_code", task_type="discovery", description=prompt)
        trajectory = self.agent.run(task)

        run_dir = Path(self.run_dir) if self.run_dir else Path(".")
        workspace = run_dir / "workspaces" / f"{task_id}_code"
        new_skill_path = workspace / "new_skill"
        if not new_skill_path.is_dir():
            new_skill_path = workspace / "workspace" / "new_skill"

        if not (new_skill_path / "SKILL.md").exists():
            self.logger.error("[Evo] Agent did not produce SKILL.md at %s", new_skill_path)
            return {"status": "failed", "reason": "no_skill_md"}

        self.logger.info("[Evo] Testing new skill at %s...", new_skill_path)
        test_ok = self._run_sandbox_tests(new_skill_path)
        if not test_ok:
            self.logger.warning("[Evo] Sandbox tests failed.")
            return {"status": "failed", "reason": "tests_failed"}

        registry = getattr(self.agent, "skill_registry", None)
        if not registry or not getattr(registry, "register_dynamic_skill", None):
            self.logger.warning("[Evo] No MatMasterSkillRegistry with register_dynamic_skill.")
            return {"status": "failed", "reason": "no_registry"}

        if registry.register_dynamic_skill(new_skill_path):
            self.logger.info("[Evo] Skill %s registered successfully.", new_skill_path.name)
            return {"status": "completed", "skill_path": str(new_skill_path)}

        self.logger.warning("[Evo] Skill evolution failed to register.")
        return {"status": "failed", "reason": "register_failed"}

    def _run_sandbox_tests(self, skill_path: Path) -> bool:
        """Run tests for the new skill in a sandbox (subprocess or temp dir). Override with real test runner."""
        raise NotImplementedError(
            "Sandbox tests not implemented. Implement _run_sandbox_tests to run the skill's tests (e.g. pytest/subprocess) "
            "and return True only if all pass; otherwise broken skills would be registered."
        )
