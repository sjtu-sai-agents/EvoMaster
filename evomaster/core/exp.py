"""EvoMaster Core - Base Classes and Common Workflows

Provides base implementations for Exp and Playground, for concrete playgrounds to inherit.
"""

import json
import logging
from pathlib import Path
from evomaster.utils.types import TaskInstance
from typing import Any


def extract_agent_response(trajectory: Any) -> str:
    """Extract the agent's final response from a trajectory (module-level utility function).

    Supports two data formats:
    - Object format (has .dialogs attribute, from runtime)
    - Dict format (JSON deserialization result, from trajectory files)

    Extraction priority:
    1. The message parameter from the finish tool_call in the last assistant message
    2. The content of the last assistant message that has content

    Args:
        trajectory: Execution trajectory (object or dict).

    Returns:
        The agent's response text; returns an empty string if extraction fails.
    """
    if not trajectory:
        return ""

    # Get dialogs (compatible with both object and dict)
    if isinstance(trajectory, dict):
        dialogs = trajectory.get("dialogs")
    elif hasattr(trajectory, "dialogs"):
        dialogs = trajectory.dialogs
    else:
        return ""

    if not dialogs:
        return ""

    last_dialog = dialogs[-1]

    # Get messages (compatible with both object and dict)
    if isinstance(last_dialog, dict):
        messages = last_dialog.get("messages", [])
    else:
        messages = getattr(last_dialog, "messages", [])

    if not messages:
        return ""

    # Iterate in reverse to find the last assistant message
    for message in reversed(messages):
        if isinstance(message, dict):
            role = message.get("role", "")
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
        else:
            role = getattr(message, "role", None)
            role = role.value if hasattr(role, "value") else str(role) if role else ""
            content = getattr(message, "content", "")
            tool_calls = getattr(message, "tool_calls", [])

        if role != "assistant":
            continue

        # Prefer checking the finish tool_call's message parameter
        for tc in (tool_calls or []):
            if isinstance(tc, dict):
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "")
            else:
                func = getattr(tc, "function", None)
                name = getattr(func, "name", "") if func else ""
                args = getattr(func, "arguments", "") if func else ""

            if name == "finish":
                try:
                    finish_args = json.loads(args) if isinstance(args, str) else args
                    finish_msg = finish_args.get("message", "")
                    if finish_msg:
                        return finish_msg
                except (json.JSONDecodeError, AttributeError):
                    pass

        # Fall back to content (skip messages with tool_calls, whose content may be leaked formatting tokens)
        if content and content.strip() and not tool_calls:
            return content

    return ""


class BaseExp:
    """Experiment base class.

    Defines the common execution logic for a single experiment.
    Concrete playgrounds can inherit and override relevant methods.
    """

    def __init__(self, agent, config):
        """Initialize the experiment.

        Args:
            agent: Agent instance.
            config: EvoMasterConfig instance.
        """
        self.agent = agent
        self.config = config
        self.results = []
        self.logger = logging.getLogger(self.__class__.__name__)
        self.run_dir = None

    @property
    def exp_name(self) -> str:
        """Get the Exp name (automatically inferred from the class name).

        Example: SolverExp -> Solver, CriticExp -> Critic.
        Subclasses can override this property to customize the name.
        """
        class_name = self.__class__.__name__
        # Remove the "Exp" suffix
        if class_name.endswith('Exp'):
            return class_name[:-3]
        return class_name

    def set_run_dir(self, run_dir: str | Path) -> None:
        """Set the run directory.

        Args:
            run_dir: Run directory path.
        """
        self.run_dir = Path(run_dir)

    def run(self, task_description: str, task_id: str = "exp_001", images: list[str] | None = None, on_step=None, resume: bool = False, trajectory_file: Path | None = None) -> dict:
        """Run a single experiment.

        Args:
            task_description: Task description.
            task_id: Task ID.
            images: List of image file paths (optional, for multimodal tasks).
            on_step: Step callback, signature (StepRecord, step_number, max_steps) -> None.
            resume: Whether to resume from a previous trajectory.
            trajectory_file: Path to the trajectory file for resume (required when resume=True).

        Returns:
            Run result dictionary.
        """
        # Create a task instance
        task = TaskInstance(
            task_id=task_id,
            task_type="discovery",
            description=task_description,
            images=images or [],
        )

        # Run the Agent (normal or resumed)
        if resume and trajectory_file:
            self.logger.info(f"Resuming task: {task_id} from {trajectory_file}")
            trajectory = self.agent.resume_from_trajectory(trajectory_file, task, on_step=on_step)
        else:
            self.logger.debug(f"Running task: {task_id}")
            trajectory = self.agent.run(task, on_step=on_step)

        # Save results
        result = {
            "task_id": task_id,
            "status": trajectory.status,
            "steps": len(trajectory.steps),
            "trajectory": trajectory,
        }
        self.results.append(result)

        return {
            "trajectory": trajectory,
            "status": trajectory.status,
            "steps": len(trajectory.steps),
        }

    def save_results(self, output_file: str):
        """Save experiment results.

        Args:
            output_file: Output file path.
        """
        output_data = []
        for result in self.results:
            output_data.append({
                "task_id": result["task_id"],
                "status": result["status"],
                "steps": result["steps"],
                "trajectory": result["trajectory"].model_dump(),
            })

        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str, ensure_ascii=False)

        self.logger.info(f"Results saved to {output_file}")


    def _extract_agent_response(self, trajectory: Any) -> str:
        """Extract the agent's final response from a trajectory.

        Args:
            trajectory: Execution trajectory.

        Returns:
            The agent's response text.
        """
        return extract_agent_response(trajectory)
