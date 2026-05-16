"""EvoMaster Agent base implementation

Provides the base abstraction for Agent, supporting tool invocation, dialog management, trajectory recording, and more.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from .context import ContextConfig, ContextManager
from evomaster.utils.llm import ContextOverflowError
from evomaster.utils.types import (
    AssistantMessage,
    Dialog,
    StepRecord,
    SystemMessage,
    TaskInstance,
    ToolMessage,
    UserMessage,
)
from evomaster.utils.llm import build_multimodal_content

if TYPE_CHECKING:
    from evomaster.utils import BaseLLM
    from .session import BaseSession
    from .tools import ToolRegistry
    from evomaster.skills import SkillRegistry


class AgentConfig(BaseModel):
    """Agent configuration"""
    max_turns: int = Field(default=100, description="Maximum number of execution turns")
    context_config: ContextConfig = Field(
        default_factory=ContextConfig,
        description="Context management configuration"
    )
    finish_on_text_response: bool = Field(
        default=False,
        description="Treat the task as completed when the LLM replies with plain text (no tool call); suitable for conversational scenarios"
    )


class BaseAgent(ABC):
    """Agent base class

    Provides the fundamental Agent functionality:
    - Dialog management (Dialog)
    - Trajectory recording (Trajectory)
    - Tool call execution
    - Context management

    Subclasses must implement:
    - _get_system_prompt(): Get the system prompt
    - _get_user_prompt(task): Get the user prompt
    """

    VERSION: str = "1.0"
    
    # Class-level trajectory file lock (mutex when multiple agent instances write to file)
    _trajectory_file_lock = threading.Lock()
    _trajectory_file_path: Path | None = None

    # Class-level current experiment info (shared by all agent instances)
    _current_exp_name: str | None = None
    _current_exp_index: int | None = None

    def __init__(
        self,
        llm: BaseLLM,
        session: BaseSession,
        tools: ToolRegistry,
        config: AgentConfig | None = None,
        skill_registry: SkillRegistry | None = None,
        output_config: dict[str, Any] | None = None,
        config_dir: Path | str | None = None,
        enable_tools: bool = True,
        enabled_tool_names: list[str] | None = None,
    ):
        """Initialize Agent

        Args:
            llm: LLM instance
            session: Environment session for executing tools
            tools: Tool registry (all tools are always registered, but only enabled tools are exposed to the LLM)
            config: Agent configuration
            skill_registry: Skill registry (optional)
            output_config: Output display configuration
            config_dir: Configuration directory path for loading prompt files
            enable_tools: Whether to include tool information in the prompt (default True). If False, tools are still registered but not exposed in the prompt
            enabled_tool_names: List of enabled tool names (optional). None or ["*"] means all registered tools are enabled.
                Only affects the tool list exposed to the LLM; does not affect manual tool calls in code.
        """
        self.llm = llm
        self.session = session
        self.tools = tools
        self.config = config or AgentConfig()
        self.skill_registry = skill_registry
        self.enable_tools = enable_tools
        self.enabled_tool_names = enabled_tool_names

        # Output configuration
        self.output_config = output_config or {}
        self.show_in_console = self.output_config.get("show_in_console", False)
        self.log_to_file = self.output_config.get("log_to_file", False)

        # Configuration directory (for loading prompt files)
        self.config_dir = Path(config_dir) if config_dir else None

        # Context manager
        self.context_manager = ContextManager(self.config.context_config)

        # Current dialog
        self.current_dialog: Dialog | None = None

        # Execution trajectory
        self.trajectory = None

        # Logger
        self.logger = logging.getLogger(self.__class__.__name__)

        # Current step count
        self._step_count = 0

        # ask_user tool buffer (intercepted and handled in the step loop)
        self._pending_ask_user: dict[str, Any] | None = None

        # Store initial system prompt and user prompt (for resetting)
        self._initial_system_prompt: str | None = None
        self._initial_user_prompt: str | None = None

        # Agent name (used to identify different agents)
        self._agent_name: str | None = None

        # Instance-level trajectory file path (independent for each agent instance)
        # self._trajectory_file_path: Path | None = None

    def run(self, task: TaskInstance, on_step=None):
        """Execute a task

        Args:
            task: Task instance
            on_step: Per-step callback with signature (StepRecord, step_number, max_steps) -> None

        Returns:
            Execution trajectory
        """
        from evomaster.utils.types import Trajectory

        self.logger.info(f"Starting task: {task.task_id}")

        # Initialize
        self._initialize(task)

        try:
            # Execution loop
            for turn in range(self.config.max_turns):
                # Clearly display the current step
                self.logger.info("=" * 80)
                self.logger.info(f"📍 Step [{turn + 1}/{self.config.max_turns}]")
                self.logger.info("=" * 80)

                should_finish = self._step()

                # Invoke step callback
                if on_step and self.trajectory and self.trajectory.steps:
                    try:
                        on_step(self.trajectory.steps[-1], turn + 1, self.config.max_turns)
                    except Exception as e:
                        self.logger.warning("on_step callback failed: %s", e)

                if should_finish:
                    self.logger.info("=" * 80)
                    if self._pending_ask_user:
                        self.logger.info("⏸️  Agent paused — waiting for user input")
                        self.trajectory.finish("waiting_for_input", self._pending_ask_user)
                        self._pending_ask_user = None
                    else:
                        self.logger.info("✅ Agent finished task")
                        self.trajectory.finish("completed")
                    self.logger.info("=" * 80)
                    break
            else:
                self.logger.warning("=" * 80)
                self.logger.warning("⚠️  Reached max turns limit")
                self.logger.warning("=" * 80)
                self.trajectory.finish("failed", {"reason": "max_turns_exceeded"})

        except Exception as e:
            self.logger.error("=" * 80)
            self.logger.error(f"❌ Agent execution failed: {e}")
            self.logger.error("=" * 80)
            self.trajectory.finish("failed", {"reason": str(e)})
            raise

        return self.trajectory

    def resume_from_trajectory(self, trajectory_file: Path, task: TaskInstance, on_step=None):
        """Resume execution from a previously interrupted run's trajectory.

        Reads the trajectory JSON, reconstructs the dialog state from the last
        fully-completed step, and continues the agent loop from there.

        Args:
            trajectory_file: Path to the trajectory.json file.
            task: TaskInstance (used for task_id and metadata only).
            on_step: Per-step callback with signature (StepRecord, step_number, max_steps) -> None.

        Returns:
            Execution trajectory.

        Raises:
            ValueError: If the trajectory has no resumable steps or is already finished.
        """
        from evomaster.utils.types import (
            Dialog,
            Trajectory,
            AssistantMessage,
            ToolMessage,
            MessageRole,
            ToolCall,
            FunctionCall,
        )

        # 1. Load trajectory data
        with open(trajectory_file, "r", encoding="utf-8") as f:
            entries = json.load(f)

        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Trajectory file is empty or invalid: {trajectory_file}")

        # 2. Find the last fully-completed entry
        resumable_index = self._find_resumable_entry(entries)

        if resumable_index is None:
            raise ValueError(
                "No resumable step found in trajectory. "
                "The task may have already completed, or all steps are incomplete."
            )

        entry = entries[resumable_index]
        entry_traj = entry.get("trajectory", {})
        step_count = entry.get("steps", 0)

        self.logger.info(f"Resuming from step {step_count} (entry {resumable_index + 1}/{len(entries)})")

        # 3. Reconstruct current_dialog from the entry
        dialog_data = entry_traj.get("dialogs", [{}])[0] if entry_traj.get("dialogs") else {}
        messages_dicts = dialog_data.get("messages", [])

        # Rebuild messages list from dicts
        restored_messages = []
        for msg_dict in messages_dicts:
            msg = self._reconstruct_message(msg_dict)
            if msg is not None:
                restored_messages.append(msg)

        # Append assistant_message from the step
        step_data = entry_traj.get("steps", [{}])[0] if entry_traj.get("steps") else {}
        assistant_dict = step_data.get("assistant_message")
        if assistant_dict:
            assistant_msg = self._reconstruct_message(assistant_dict)
            if assistant_msg is not None:
                restored_messages.append(assistant_msg)

        # Append tool_responses
        for tr_dict in step_data.get("tool_responses", []):
            tr_msg = self._reconstruct_message(tr_dict)
            if tr_msg is not None:
                restored_messages.append(tr_msg)

        # Build the dialog with restored messages
        self.current_dialog = Dialog(
            messages=restored_messages,
            tools=self._get_tool_specs(),
        )

        self.logger.info(f"Restored dialog with {len(restored_messages)} messages")

        # 4. Set state
        self._step_count = step_count
        self._pending_ask_user = None

        # 5. Create a new Trajectory for the resumed run
        self.trajectory = Trajectory(
            task_id=task.task_id,
            meta={
                "agent_version": self.VERSION,
                "task_type": task.task_type,
                "resumed_from_step": step_count,
                "resumed_from_file": str(trajectory_file),
            },
        )
        self.trajectory.dialogs.append(self.current_dialog)

        # 6. Continue the execution loop
        remaining_turns = self.config.max_turns - step_count
        if remaining_turns <= 0:
            self.logger.warning("No remaining turns after resume (step_count=%d, max_turns=%d)",
                                step_count, self.config.max_turns)
            self.trajectory.finish("failed", {"reason": "no_remaining_turns_after_resume"})
            return self.trajectory

        try:
            for turn in range(remaining_turns):
                self.logger.info("=" * 80)
                self.logger.info(f"📍 Step [{step_count + turn + 1}/{self.config.max_turns}] (resumed)")
                self.logger.info("=" * 80)

                should_finish = self._step()

                if on_step and self.trajectory and self.trajectory.steps:
                    try:
                        on_step(self.trajectory.steps[-1], step_count + turn + 1, self.config.max_turns)
                    except Exception as e:
                        self.logger.warning("on_step callback failed: %s", e)

                if should_finish:
                    self.logger.info("=" * 80)
                    if self._pending_ask_user:
                        self.logger.info("⏸️  Agent paused — waiting for user input")
                        self.trajectory.finish("waiting_for_input", self._pending_ask_user)
                        self._pending_ask_user = None
                    else:
                        self.logger.info("✅ Agent finished task")
                        self.trajectory.finish("completed")
                    self.logger.info("=" * 80)
                    break
            else:
                self.logger.warning("=" * 80)
                self.logger.warning("⚠️  Reached max turns limit")
                self.logger.warning("=" * 80)
                self.trajectory.finish("failed", {"reason": "max_turns_exceeded"})

        except Exception as e:
            self.logger.error("=" * 80)
            self.logger.error(f"❌ Agent execution failed: {e}")
            self.logger.error("=" * 80)
            self.trajectory.finish("failed", {"reason": str(e)})
            raise

        return self.trajectory

    @staticmethod
    def _find_resumable_entry(entries: list[dict]) -> int | None:
        """Find the index of the last resumable entry in the trajectory.

        A resumable entry is one where:
        - It has an assistant_message
        - All tool_calls have corresponding tool_responses
        - It is NOT a finish/ask_user call (those indicate task already ended)

        Args:
            entries: List of trajectory entry dicts.

        Returns:
            Index of the last resumable entry, or None if none found.
        """
        for i in range(len(entries) - 1, -1, -1):
            entry = entries[i]
            entry_traj = entry.get("trajectory", {})
            steps_data = entry_traj.get("steps", [])

            if not steps_data:
                continue

            step = steps_data[0]
            assistant = step.get("assistant_message")
            if not assistant:
                continue

            # Check if this was a finish call — skip it (task already done)
            tool_calls = assistant.get("tool_calls") or []
            for tc in tool_calls:
                func = tc.get("function", {})
                if func.get("name") in ("finish", "ask_user"):
                    break
            else:
                # No finish/ask_user call — this entry is resumable
                return i

        return None

    @staticmethod
    def _reconstruct_message(msg_dict: dict):
        """Reconstruct a Message object from a serialized dict.

        Args:
            msg_dict: Serialized message dictionary.

        Returns:
            Reconstructed Message instance, or None if role is unknown.
        """
        role_str = msg_dict.get("role", "")
        content = msg_dict.get("content")
        meta = msg_dict.get("meta", {})

        try:
            role = MessageRole(role_str)
        except ValueError:
            return None

        if role == MessageRole.SYSTEM:
            return SystemMessage(content=content, meta=meta)
        elif role == MessageRole.USER:
            return UserMessage(content=content, meta=meta)
        elif role == MessageRole.ASSISTANT:
            tool_calls = None
            raw_tool_calls = msg_dict.get("tool_calls")
            if raw_tool_calls:
                tool_calls = []
                for tc in raw_tool_calls:
                    func = tc.get("function", {})
                    tool_calls.append(ToolCall(
                        id=tc.get("id", ""),
                        function=FunctionCall(
                            name=func.get("name", ""),
                            arguments=func.get("arguments", ""),
                        ),
                    ))
            reasoning_content = msg_dict.get("reasoning_content")
            return AssistantMessage(
                content=content,
                meta=meta,
                tool_calls=tool_calls,
                reasoning_content=reasoning_content,
            )
        elif role == MessageRole.TOOL:
            return ToolMessage(
                content=content,
                meta=meta,
                tool_call_id=msg_dict.get("tool_call_id", ""),
                name=msg_dict.get("name", ""),
            )

        return None

    def continue_run(self, user_message: str, on_step=None):
        """Append a user message to the existing dialog and continue the step loop.

        Unlike run(), this does not call _initialize() and preserves the existing dialog context.
        Suitable for multi-turn conversation scenarios (e.g., Feishu Bot), where a new message
        continues the conversation after the previous round finishes.

        Args:
            user_message: New user message
            on_step: Per-step callback with signature (StepRecord, step_number, max_steps) -> None

        Returns:
            Execution trajectory for this round

        Raises:
            ValueError: If the agent has not been initialized via run()
        """
        from evomaster.utils.types import Trajectory

        if self.current_dialog is None:
            raise ValueError(
                "Agent not initialized. Call run() first before continue_run()."
            )

        self.logger.info("Continuing conversation with new user message")

        # Append user message to existing dialog
        self.add_user_message(user_message)

        # Create a new Trajectory for this round (for tracking and reporting)
        self.trajectory = Trajectory(
            task_id=f"continue_{self._step_count}",
            meta={
                "agent_version": self.VERSION,
                "task_type": "chat_continue",
            },
        )
        self.trajectory.dialogs.append(self.current_dialog)

        # Reset step count
        self._step_count = 0

        try:
            for turn in range(self.config.max_turns):
                self.logger.info("=" * 80)
                self.logger.info(f"📍 Step [{turn + 1}/{self.config.max_turns}]")
                self.logger.info("=" * 80)

                should_finish = self._step()

                if on_step and self.trajectory and self.trajectory.steps:
                    try:
                        on_step(self.trajectory.steps[-1], turn + 1, self.config.max_turns)
                    except Exception as e:
                        self.logger.warning("on_step callback failed: %s", e)

                if should_finish:
                    self.logger.info("=" * 80)
                    if self._pending_ask_user:
                        self.logger.info("⏸️  Agent paused — waiting for user input")
                        self.trajectory.finish("waiting_for_input", self._pending_ask_user)
                        self._pending_ask_user = None
                    else:
                        self.logger.info("✅ Agent finished task")
                        self.trajectory.finish("completed")
                    self.logger.info("=" * 80)
                    break
            else:
                self.logger.warning("=" * 80)
                self.logger.warning("⚠️  Reached max turns limit")
                self.logger.warning("=" * 80)
                self.trajectory.finish("failed", {"reason": "max_turns_exceeded"})

        except Exception as e:
            self.logger.error("=" * 80)
            self.logger.error(f"❌ Agent execution failed: {e}")
            self.logger.error("=" * 80)
            self.trajectory.finish("failed", {"reason": str(e)})
            raise

        return self.trajectory

    def _initialize(self, task: TaskInstance) -> None:
        """Initialize the execution environment

        Args:
            task: Task instance
        """
        from evomaster.utils.types import Trajectory

        # Create trajectory
        self.trajectory = Trajectory(
            task_id=task.task_id,
            meta={
                "agent_version": self.VERSION,
                "task_type": task.task_type,
            }
        )

        # Get initial prompts
        system_prompt = self._get_system_prompt()
        user_prompt = self._get_user_prompt(task)

        # Save initial prompts (for resetting)
        self._initial_system_prompt = system_prompt
        self._initial_user_prompt = user_prompt

        # Build user message content: construct multimodal content if the task includes images
        if task.images:
            user_content = build_multimodal_content(user_prompt, task.images)
        else:
            user_content = user_prompt

        # Create dialog
        self.current_dialog = Dialog(
            messages=[
                SystemMessage(content=system_prompt),
                UserMessage(content=user_content),
            ],
            tools=self._get_tool_specs(),
        )
        # breakpoint()

        self.trajectory.dialogs.append(self.current_dialog)
        self._step_count = 0

    def _step(self) -> bool:
        """Execute one step

        Returns:
            Whether the execution should finish (True means finish)
        """
        self._step_count += 1

        # Prepare dialog (may need truncation)
        dialog_for_query, compacted = self.context_manager.prepare_for_query(self.current_dialog)

        # If permanent compaction was performed (summary/truncate), write back to current_dialog
        # prune is only a temporary view (compacted=False), not written back, preserving full tool output for future summary use
        if compacted:
            self.current_dialog = dialog_for_query
            self.context_manager.reset_prompt_tokens()
            # Sync update the trajectory reference to prevent extract_agent_response from reading a stale dialog
            if self.trajectory and self.trajectory.dialogs:
                self.trajectory.dialogs[-1] = self.current_dialog

        # Query the model (using LLM) -- passive recovery: catch ContextOverflowError, perform emergency compaction, and retry
        try:
            assistant_message = self.llm.query(dialog_for_query)
        except ContextOverflowError:
            self.logger.warning(
                "Context overflow detected, performing emergency compaction and retrying"
            )
            self.current_dialog = self.context_manager.truncate(self.current_dialog)
            self.context_manager.reset_prompt_tokens()
            if self.trajectory and self.trajectory.dialogs:
                self.trajectory.dialogs[-1] = self.current_dialog
            dialog_for_query = self.current_dialog
            assistant_message = self.llm.query(dialog_for_query)

        # Record actual prompt_tokens, used by the next prepare_for_query call to determine whether compaction is needed
        usage = assistant_message.meta.get("usage")
        if usage:
            self.context_manager.update_usage(
                usage, msg_count=len(dialog_for_query.messages)
            )

            # Proactive check: following OpenCode's isOverflow approach, use actual usage to determine whether compaction is needed
            # Even if the current call succeeds, if token usage is close to the limit, compact proactively to avoid overflow next time
            if self.context_manager.is_overflow(usage):
                self.logger.info(
                    "Token usage near limit (total=%s), proactive compaction",
                    usage.get("total_tokens") or (
                        usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                    ),
                )
                self.current_dialog = self.context_manager.truncate(self.current_dialog)
                self.context_manager.reset_prompt_tokens()
                if self.trajectory and self.trajectory.dialogs:
                    self.trajectory.dialogs[-1] = self.current_dialog

        self.current_dialog.add_message(assistant_message)

        # Create step record
        step_record = StepRecord(
            step_id=self._step_count,
            assistant_message=assistant_message,
        )

        # If there are no tool calls
        if not assistant_message.tool_calls:
            # Check whether the Agent has tool calling enabled
            # If tools are not enabled (enable_tools=False), finish directly
            # because this type of Agent only needs to provide an answer without tool calls
            # Similarly, when finish_on_text_response=True, also finish directly (conversational scenario)
            if (hasattr(self, 'enable_tools') and not self.enable_tools) or \
               self.config.finish_on_text_response:
                self.trajectory.add_step(step_record)
                # Append and save this step to the trajectory file (including tool_responses)
                self._append_trajectory_entry(dialog_for_query, step_record)
                return True  # Finish directly

            # If tools are enabled but no tool calls were made, prompt to continue
            self._handle_no_tool_call()
            self.trajectory.add_step(step_record)
            # Append and save this step to the trajectory file (including tool_responses)
            self._append_trajectory_entry(dialog_for_query, step_record)
            return False

        # Process tool calls
        should_finish = False
        for tool_call in assistant_message.tool_calls:
            self.logger.debug(f"Processing tool call: {tool_call.function.name}")

            # Check if this is the finish tool
            if tool_call.function.name == "finish":
                # Print the finish tool's arguments (final answer)
                try:
                    finish_args = json.loads(tool_call.function.arguments)
                    self.logger.info("=" * 80)
                    self.logger.info("📝 Finish Tool Arguments:")
                    for key, value in finish_args.items():
                        value_str = str(value)
                        self.logger.info(f"  {key}: {value_str}")
                    self.logger.info("=" * 80)
                except Exception as e:
                    self.logger.info(f"📝 Finish Tool Raw Args: {tool_call.function.arguments}")
                should_finish = True

                # Create a ToolMessage for the finish tool to ensure dialog history is valid during continue_run
                tool_message = ToolMessage(
                    content="Task marked as finished.",
                    tool_call_id=tool_call.id,
                    name=tool_call.function.name,
                    meta={"info": {"task_completed": True}}
                )
                self.current_dialog.add_message(tool_message)
                step_record.tool_responses.append(tool_message)

                break

            # Check if this is the ask_user tool (pause execution, wait for user response)
            elif tool_call.function.name == "ask_user":
                try:
                    ask_args = json.loads(tool_call.function.arguments)
                    self._pending_ask_user = {
                        "ask_user": True,
                        "questions": ask_args.get("questions", []),
                    }
                except (json.JSONDecodeError, KeyError):
                    self._pending_ask_user = {"ask_user": True, "questions": []}

                self.logger.info("=" * 80)
                self.logger.info("❓ ask_user: Agent is asking user for clarification")
                self.logger.info("=" * 80)

                tool_message = ToolMessage(
                    content="Questions sent to user. Waiting for response.",
                    tool_call_id=tool_call.id,
                    name="ask_user",
                    meta={"info": self._pending_ask_user},
                )
                self.current_dialog.add_message(tool_message)
                step_record.tool_responses.append(tool_message)
                should_finish = True
                break

            # Execute tool
            observation, info = self._execute_tool(tool_call)

            # Truncate excessively long tool output to prevent context overflow
            MAX_TOOL_OUTPUT = 30000
            if len(observation) > MAX_TOOL_OUTPUT:
                observation = (
                    observation[:MAX_TOOL_OUTPUT // 2]
                    + "\n\n... [output truncated due to length] ...\n\n"
                    + observation[-MAX_TOOL_OUTPUT // 2:]
                )

            # Create tool response message
            tool_message = ToolMessage(
                content=observation,
                tool_call_id=tool_call.id,
                name=tool_call.function.name,
                meta={"info": info}
            )

            self.current_dialog.add_message(tool_message)
            step_record.tool_responses.append(tool_message)

        self.trajectory.add_step(step_record)
        # Append and save this step to the trajectory file (including tool_responses)
        self._append_trajectory_entry(dialog_for_query, step_record)
        return should_finish

    def _execute_tool(self, tool_call) -> tuple[str, dict[str, Any]]:
        """Execute a tool call

        Args:
            tool_call: Tool call

        Returns:
            (observation, info) tuple
        """
        tool_name = tool_call.function.name
        tool_args = tool_call.function.arguments

        # Log tool call start
        self._log_tool_start(tool_name, tool_args)

        # Get tool and execute
        tool = self.tools.get_tool(tool_name)
        if tool is None:
            error_msg = f"Unknown tool: {tool_name}"
            self._log_tool_end(tool_name, error_msg, {"error": "tool_not_found"})
            return error_msg, {"error": "tool_not_found"}

        try:
            # Execute tool
            observation, info = tool.execute(self.session, tool_args)

            # Truncate excessively long tool output (keep first 15000 + last 15000 when exceeding 30000 characters)
            if len(observation) > 30000:
                observation = (
                    observation[:15000]
                    + "\n...[truncated]...\n"
                    + observation[-15000:]
                )

            # Log tool call end
            self._log_tool_end(tool_name, observation, info)
            
            return observation, info
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            self.logger.error(f"Tool execution failed: {e}", exc_info=True)
            self._log_tool_end(tool_name, error_msg, {"error": str(e)})
            return error_msg, {"error": str(e)}

    def _log_tool_start(self, tool_name: str, tool_args: str) -> None:
        """Log tool call start"""
        if self.log_to_file:
            self.logger.info("=" * 80)
            self.logger.info(f"Tool Call Start: {tool_name}")
            self.logger.info(f"Arguments: {tool_args}")
            self.logger.info("=" * 80)
        
        if self.show_in_console:
            print(f"\n[Tool Call] {tool_name}")
            if tool_args:
                # Try to format JSON arguments
                try:
                    args_dict = json.loads(tool_args)
                    print(f"  Arguments: {json.dumps(args_dict, indent=2, ensure_ascii=False)}")
                except:
                    print(f"  Arguments: {tool_args}")
            print("-" * 60)

    def _log_tool_end(self, tool_name: str, observation: str, info: dict[str, Any]) -> None:
        """Log tool call end"""
        obs_display = observation
        if self.log_to_file:
            self.logger.info("=" * 80)
            self.logger.info(f"Tool Call End: {tool_name}")
            self.logger.info(f"Output: {obs_display}")
            if info:
                self.logger.info(f"Info: {info}")
            self.logger.info("=" * 80)
        
        if self.show_in_console:
            print(f"\n[Tool Output] {tool_name}")
            print("-" * 60)
            print(obs_display)
            print("-" * 60)

    def _handle_no_tool_call(self) -> None:
        """Handle the case when there are no tool calls"""
        # Add a user message prompting to continue
        prompt = (
            "Please continue working on the task.\n"
            "When you have completed the task, use the finish tool.\n"
            "IMPORTANT: You should not ask for human help."
        )
        self.current_dialog.add_message(UserMessage(content=prompt))


    def _get_tool_specs(self) -> list:
        """Get the list of tool specifications

        Only returns the tool specification list when enable_tools=True.
        If enable_tools=False, returns an empty list (tools are still registered but not exposed in the prompt).
        If enabled_tool_names is set, only returns specifications for the enabled tools.
        """
        if not self.enable_tools:
            return []
        else:
            all_specs = self.tools.get_tool_specs()
            self.logger.info("All tool names:")
            self.logger.info([spec.function.name for spec in all_specs])
            if self.enabled_tool_names:
                filtered_specs = [spec for spec in all_specs if spec.function.name in self.enabled_tool_names]
                self.logger.info("Enabled tool names:")
                self.logger.info([spec.function.name for spec in filtered_specs])
                return filtered_specs
            else:
                # If enabled_tool_names is not specified, return all tools
                return all_specs

    def load_prompt_from_file(
        self,
        prompt_file: str | Path,
        format_kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Load a prompt from a file

        Supports relative paths (relative to config_dir) and absolute paths.
        Supports string formatting with format_kwargs ({} placeholders).

        Args:
            prompt_file: Prompt file path (relative or absolute)
            format_kwargs: Dictionary of parameters for formatting the prompt (optional)

        Returns:
            Prompt content (formatted)

        Examples:
            >>> agent.load_prompt_from_file("prompts/system_prompt.txt")
            >>> agent.load_prompt_from_file("prompts/user_prompt.txt", {"task": "complete the code task"})
        """
        # Resolve file path
        prompt_path = Path(prompt_file)
        if not prompt_path.is_absolute():
            if self.config_dir is None:
                raise ValueError(
                    "config_dir not set. Cannot resolve relative path. "
                    "Please provide config_dir in __init__ or use absolute path."
                )
            prompt_path = self.config_dir / prompt_file

        # Read file content
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}\n"
                f"Please create the file or check the path."
            )

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read()

            # If format_kwargs are provided, perform formatting
            if format_kwargs:
                try:
                    prompt_content = prompt_content.format(**format_kwargs)
                except KeyError as e:
                    self.logger.warning(
                        f"Format key {e} not found in format_kwargs. "
                        f"Available keys: {list(format_kwargs.keys())}"
                    )
                    raise

            self.logger.debug(f"Loaded prompt from: {prompt_path}")
            return prompt_content
        except Exception as e:
            raise RuntimeError(f"Failed to load prompt from {prompt_path}: {e}")

    def reset_context(self) -> None:
        """Reset the Agent's context to its initial state

        Resets the dialog to contain only the initial system prompt and user prompt.
        Requires prior initialization via initialize or manual setting of _initial_system_prompt and _initial_user_prompt.
        """
        if self._initial_system_prompt is None:
            raise ValueError(
                "Cannot reset context: initial prompts not set. "
                "Please initialize the agent first or set _initial_system_prompt manually."
            )

        # Re-create dialog
        messages = [SystemMessage(content=self._initial_system_prompt)]
        if self._initial_user_prompt:
            messages.append(UserMessage(content=self._initial_user_prompt))

        self.current_dialog = Dialog(
            messages=messages,
            tools=self._get_tool_specs(),
        )

        # Reset step count
        self._step_count = 0

        self.logger.info("Context reset to initial state")

    def add_user_message(self, content: str) -> None:
        """Add a user message to the current dialog

        Args:
            content: User message content
        """
        if self.current_dialog is None:
            raise ValueError(
                "No active dialog. Please initialize the agent first."
            )

        user_message = UserMessage(content=content)
        self.current_dialog.add_message(user_message)
        self.logger.debug(f"Added user message: {content[:50]}...")

    def add_assistant_message(self, content: str, tool_calls: list | None = None) -> None:
        """Add an assistant message to the current dialog

        Args:
            content: Assistant message content
            tool_calls: Tool call list (optional)
        """
        if self.current_dialog is None:
            raise ValueError(
                "No active dialog. Please initialize the agent first."
            )

        assistant_message = AssistantMessage(content=content, tool_calls=tool_calls or [])
        self.current_dialog.add_message(assistant_message)
        content_preview = content[:50] if content else "(empty)"
        self.logger.debug(f"Added assistant message: {content_preview}...")

    def add_tool_message(
        self,
        content: str,
        tool_call_id: str,
        name: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Add a tool message to the current dialog

        Args:
            content: Tool execution result
            tool_call_id: Tool call ID
            name: Tool name
            meta: Metadata (optional)
        """
        if self.current_dialog is None:
            raise ValueError(
                "No active dialog. Please initialize the agent first."
            )

        tool_message = ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            meta=meta or {},
        )
        self.current_dialog.add_message(tool_message)
        self.logger.debug(f"Added tool message: {name}")

    def set_next_user_request(self, content: str) -> None:
        """Set the user request for the next conversation turn

        This adds a user message to the current dialog.

        Args:
            content: User request content
        """
        self.add_user_message(content)

    def get_current_dialog(self) -> Dialog | None:
        """Get the current dialog

        Returns:
            Current dialog object, or None if not initialized
        """
        return self.current_dialog

    def get_conversation_history(self) -> list:
        """Get conversation history

        Returns:
            List of messages
        """
        if self.current_dialog is None:
            return []
        return self.current_dialog.messages.copy()
    
    @classmethod
    def set_trajectory_file_path(cls, trajectory_file_path: str | Path) -> None:
        """Set the trajectory file path

        Args:
            trajectory_file_path: Trajectory file path
        """
        cls._trajectory_file_path = Path(trajectory_file_path)
        # Ensure directory exists
        cls._trajectory_file_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def set_exp_info(cls, exp_name: str, exp_index: int) -> None:
        """Set the current experiment info (class-level, shared by all agent instances)

        Called during experiment execution, used to record which experiment stage and iteration the current step belongs to.

        Args:
            exp_name: Experiment stage name (e.g., "Solver", "Critic", "Rewriter", "Selector")
            exp_index: Iteration index (e.g., 0, 1, 2, 3, 4)
        """
        cls._current_exp_name = exp_name
        cls._current_exp_index = exp_index
    
    def set_agent_name(self, name: str) -> None:
        """Set the Agent name (used to identify different agents)

        Args:
            name: Agent name
        """
        self._agent_name = name
    
    def _append_trajectory_entry(self, dialog_for_query: Dialog, step_record: "StepRecord") -> None:
        """Append a trajectory entry to the trajectory file

        After each step completes, appends the prompt, response, and tool_responses to the trajectory file.
        Uses a file lock to ensure thread safety when multiple agents write to the same file.

        The save format is consistent with the existing trajectory format:
        [
            {
                "task_id": "...",
                "status": "...",
                "steps": ...,
                "trajectory": {...}
            }
        ]

        Each step appends a new entry containing the prompt, response, and tool_responses for this call.

        Args:
            dialog_for_query: Dialog sent to the LLM (prompt)
            step_record: Step record (containing assistant_message and tool_responses)
        """
        if self._trajectory_file_path is None:
            return

        try:
            with self._trajectory_file_lock:
                # Read existing data
                existing_data = []
                if self._trajectory_file_path.exists():
                    try:
                        with open(self._trajectory_file_path, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                    except (json.JSONDecodeError, FileNotFoundError):
                        # If the file is corrupted or does not exist, start with an empty list
                        existing_data = []

                # Build a new trajectory entry
                # Format is consistent with the existing trajectory format, but saves per-LLM-call information
                task_id = self.trajectory.task_id if self.trajectory else "unknown"
                status = self.trajectory.status if self.trajectory else "running"

                # Convert dialog_for_query to dictionary format
                prompt_dict = dialog_for_query.model_dump() if hasattr(dialog_for_query, 'model_dump') else {
                    "messages": [
                        {
                            "role": msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                            "content": msg.content if hasattr(msg, 'content') else str(msg)
                        }
                        for msg in dialog_for_query.messages
                    ],
                    "tools": dialog_for_query.tools if hasattr(dialog_for_query, 'tools') else []
                }

                # Get assistant_message from step_record
                assistant_message = step_record.assistant_message

                # Convert assistant_message to dictionary format
                response_dict = assistant_message.model_dump() if hasattr(assistant_message, 'model_dump') else {
                    "role": assistant_message.role.value if hasattr(assistant_message.role, 'value') else str(assistant_message.role),
                    "content": assistant_message.content if hasattr(assistant_message, 'content') else "",
                    "tool_calls": [
                        {
                            "id": tc.id if hasattr(tc, 'id') else "",
                            "function": {
                                "name": tc.function.name if hasattr(tc.function, 'name') else "",
                                "arguments": tc.function.arguments if hasattr(tc.function, 'arguments') else ""
                            }
                        }
                        for tc in (assistant_message.tool_calls or [])
                    ] if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls else []
                }

                # Convert tool_responses to dictionary format
                tool_responses_list = []
                for tr in step_record.tool_responses:
                    tr_dict = tr.model_dump() if hasattr(tr, 'model_dump') else {
                        "role": "tool",
                        "content": tr.content if hasattr(tr, 'content') else "",
                        "tool_call_id": tr.tool_call_id if hasattr(tr, 'tool_call_id') else "",
                        "name": tr.name if hasattr(tr, 'name') else ""
                    }
                    tool_responses_list.append(tr_dict)

                # Build trajectory entry, format consistent with existing trajectory format
                entry = {
                    "task_id": f"{task_id}_{self._agent_name or 'agent'}_step_{self._step_count}",
                    "exp_name": self._current_exp_name,      # experiment stage name
                    "exp_index": self._current_exp_index,    # experiment iteration index
                    "status": status,
                    "steps": self._step_count,
                    "trajectory": {
                        "task_id": task_id,
                        "agent_name": self._agent_name or "unknown",
                        "step": self._step_count,
                        "dialogs": [prompt_dict],  # Save the prompt of this call
                        "steps": [
                            {
                                "step_id": self._step_count,
                                "assistant_message": response_dict,  # Save the response of this call
                                "tool_responses": tool_responses_list,  # Save tool responses
                                "meta": {}
                            }
                        ],
                        "start_time": None,
                        "end_time": None,
                        "status": status,
                        "result": {
                            "prompt": prompt_dict,
                            "response": response_dict
                        },
                        "meta": {
                            "agent_version": self.VERSION,
                            "agent_name": self._agent_name or "unknown",
                            "step": self._step_count
                        }
                    }
                }

                # Append new entry
                existing_data.append(entry)

                # Write back to file
                with open(self._trajectory_file_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, indent=2, default=str, ensure_ascii=False)

        except Exception as e:
            # If saving fails, only log a warning without interrupting execution
            self.logger.warning(f"Failed to append trajectory entry: {e}", exc_info=True)

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Get the system prompt

        Subclasses must implement this method.
        """
        pass

    @abstractmethod
    def _get_user_prompt(self, task: TaskInstance) -> str:
        """Get the user prompt

        Subclasses must implement this method.

        Args:
            task: Task instance
        """
        pass


class Agent(BaseAgent):
    """Standard Agent implementation

    Uses configurable prompt templates.
    Supports loading prompts from configuration files.
    """

    def __init__(
        self,
        llm: BaseLLM,
        session: BaseSession,
        tools: ToolRegistry,
        system_prompt_file: str | Path | None = None,
        user_prompt_file: str | Path | None = None,
        prompt_format_kwargs: dict[str, Any] | None = None,
        config: AgentConfig | None = None,
        skill_registry: SkillRegistry | None = None,
        output_config: dict[str, Any] | None = None,
        config_dir: Path | str | None = None,
        enable_tools: bool = True,
        enabled_tool_names: list[str] | None = None,
    ):
        """Initialize Agent

        Args:
            llm: LLM instance
            session: Environment session
            tools: Tool registry
            system_prompt_file: System prompt file path (relative to config_dir or absolute)
            user_prompt_file: User prompt file path (relative to config_dir or absolute)
            prompt_format_kwargs: Dictionary of parameters for formatting prompts ({} placeholders)
            config: Agent configuration
            skill_registry: Skill registry (optional)
            output_config: Output display configuration
            config_dir: Configuration directory path for loading prompt files
            enable_tools: Whether to include tool information in the prompt (default True). If False, tools are still registered but not exposed in the prompt, and the Agent will not call tools
            enabled_tool_names: List of enabled tool names (optional). None or ["*"] means all registered tools are enabled.
        """
        super().__init__(llm, session, tools, config, skill_registry, output_config, config_dir=config_dir, enable_tools=enable_tools, enabled_tool_names=enabled_tool_names)

        # Store prompts
        self._system_prompt: str | None = None
        self._user_prompt: str | None = None
        self._prompt_format_kwargs = prompt_format_kwargs or {}
        
        # Load system prompt (priority: system_prompt_file > default)
        if system_prompt_file:
            self._system_prompt = self.load_prompt_from_file(
                system_prompt_file,
                format_kwargs=self._prompt_format_kwargs
            )
        else:
            self._system_prompt = self._default_system_prompt()
        
        # Load user prompt (optional)
        if user_prompt_file:
            self._user_prompt = self.load_prompt_from_file(
                user_prompt_file,
                format_kwargs=self._prompt_format_kwargs
            )

    def _default_system_prompt(self) -> str:
        """Default system prompt"""
        prompt = """You are a helpful AI assistant that can execute tasks using tools.

You have access to the following tools:
- execute_bash: Execute bash commands in a terminal
- str_replace_editor: View, create, and edit files
- think: Think about the problem (does not affect the environment)
- finish: Signal that you have completed the task

When you need to complete a task:
1. First understand what needs to be done
2. Check if any available skills can help you
3. Use the available tools to accomplish the task
4. When finished, use the finish tool to signal completion

Always be careful with file operations and bash commands.
"""
        return prompt

    def _get_system_prompt(self) -> str:
        """Get the system prompt, dynamically adding working directory information"""
        working_dir = self.session.get_workspace_path()
        if working_dir is None:
            working_dir = self.session.config.workspace_path
        working_dir_abs = str(Path(working_dir).absolute())
        working_dir_info = f"\n\nImportant: The current working directory is {working_dir_abs}. You must perform all operations in this directory and cannot change the working directory. All file operations and command executions must be performed within the working directory {working_dir_abs}."
        prompt = self._system_prompt + working_dir_info
        return prompt

    def _get_user_prompt(self, task: TaskInstance) -> str:
        """Get the user prompt"""
        # If a user prompt is set, use it (may contain {} placeholders)
        if self._user_prompt:
            try:
                return self._user_prompt.format(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    description=task.description,
                    input_data=task.input_data,
                    **self._prompt_format_kwargs
                )
            except KeyError:
                # If formatting fails, return as-is (may not have placeholders)
                return self._user_prompt
        
        # Default user prompt
        return f"""Please complete the following task:

Task ID: {task.task_id}
Task Type: {task.task_type}
Description: {task.description}

Additional Information:
{task.input_data}
"""

    def _get_tool_specs(self) -> list:
        """Get the list of tool specifications

        Overrides the base class method, calls the base class implementation.
        """
        return super()._get_tool_specs()
