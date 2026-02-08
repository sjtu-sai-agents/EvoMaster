"""ResearchPlanner: deterministic flight-plan execution under CRP (Computational Resource Protocol).

- Loads industrial-grade system prompt from prompts/planner_system_prompt.txt.
- Injects hard-coded CRP (license firewall, tool stack); validates plan JSON; enforces human-in-the-loop for high-cost steps.
- Persists state to research_state.json; supports resume.
"""

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from evomaster.core.exp import BaseExp
from evomaster.utils.types import Dialog, SystemMessage, UserMessage

from .direct_solver import DirectSolver, _get_available_tool_names

# === CRP: immutable protocol (no config override) ===
INTERNAL_CRP_CONTEXT = {
    "Protocol_Name": "MatMaster_CRP_v1.0",
    "License_Registry": {
        "Allow_List": ["ABACUS", "LAMMPS", "DPA", "CP2K", "OpenBabel", "mat_abacus", "mat_dpa", "mat_sg", "mat_doc", "mat_sn"],
        "Block_List": ["VASP", "Gaussian", "CASTEP", "Wien2k"],
        "Policy": "Strict_Block_Execution",
    },
    "Tool_Stack": {
        "Preferred_DFT": "ABACUS",
        "Preferred_MLP": "DPA",
        "Preferred_MD": "LAMMPS",
    },
}


def _get_mat_master_config(config) -> dict:
    try:
        if hasattr(config, "model_dump"):
            d = config.model_dump()
        else:
            d = dict(config) if config else {}
        return d.get("mat_master") or {}
    except Exception:
        return {}


def _is_deg_plan(plan: Any) -> bool:
    """True if plan is a DEG (has 'steps' or 'execution_graph' with step_id)."""
    if not isinstance(plan, dict):
        return False
    steps = plan.get("steps") or plan.get("execution_graph")
    return isinstance(steps, list) and len(steps) > 0 and isinstance(steps[0].get("step_id"), int)


def _normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    """Map execution_graph schema to internal steps schema."""
    intensity = (step.get("compute_intensity") or step.get("compute_cost") or "MEDIUM").upper()
    if intensity == "LOW":
        cost = "Low"
    elif intensity == "HIGH":
        cost = "High"
    else:
        cost = "Medium"
    return {
        "step_id": step.get("step_id"),
        "tool_name": step.get("tool_name", ""),
        "intent": step.get("scientific_intent") or step.get("intent", ""),
        "compute_cost": cost,
        "requires_human_confirm": step.get("requires_confirmation", step.get("requires_human_confirm", False)),
        "fallback_logic": step.get("fallback_strategy") or step.get("fallback_logic", "None"),
        "status": step.get("status", "pending"),
    }


def _normalize_plan(plan: dict[str, Any], max_steps: int = 999) -> dict[str, Any]:
    """Ensure plan has 'steps' with internal field names; cap length."""
    graph = plan.get("execution_graph") or plan.get("steps") or []
    plan["steps"] = [_normalize_step(s) for s in graph][:max_steps]
    for s in plan["steps"]:
        s.setdefault("status", "pending")
    return plan


def _plan_to_external_schema(plan: dict[str, Any]) -> dict[str, Any]:
    """Convert internal plan (steps) to prompt schema (execution_graph) for revision/display."""
    steps = plan.get("steps", [])
    intensity_map = {"Low": "LOW", "Medium": "MEDIUM", "High": "HIGH"}
    execution_graph = [
        {
            "step_id": s.get("step_id"),
            "tool_name": s.get("tool_name", ""),
            "scientific_intent": s.get("intent", ""),
            "compute_intensity": intensity_map.get(s.get("compute_cost"), "MEDIUM"),
            "requires_confirmation": s.get("requires_human_confirm", False),
            "fallback_strategy": s.get("fallback_logic", "None"),
        }
        for s in steps
    ]
    return {
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "refusal_reason": plan.get("refusal_reason"),
        "strategy_name": plan.get("strategy_name"),
        "fidelity_level": plan.get("fidelity_level", "Production"),
        "execution_graph": execution_graph,
    }


def _extract_json_from_content(content: str) -> str | None:
    """Extract first {...} or ```json ... ``` from LLM output."""
    text = (content or "").strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class ResearchPlanner(BaseExp):
    """Plan-execute under CRP: flight plan (JSON DEG) → validate → optional pre-flight confirm → execute steps via DirectSolver."""

    def __init__(self, agent, config):
        super().__init__(agent, config)
        self.logger = logging.getLogger("MatMaster.Planner")
        mat = _get_mat_master_config(config)
        planner_cfg = mat.get("planner") or {}
        self.state_file = planner_cfg.get("state_file", "research_state.json")
        self.max_steps = planner_cfg.get("max_steps", 20)
        self.human_check = planner_cfg.get("human_check_step", True)

    def _run_dir_path(self) -> Path:
        return Path(self.run_dir) if self.run_dir else Path(".")

    def _state_path(self, task_id: str) -> Path:
        base = self._run_dir_path()
        workspaces = base / "workspaces" / task_id
        workspaces.mkdir(parents=True, exist_ok=True)
        return workspaces / self.state_file

    def _load_state(self, task_id: str) -> dict[str, Any]:
        path = self._state_path(task_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning("Failed to load state: %s", e)
        return {"goal": "", "plan": None, "history": []}

    def _save_state(self, task_id: str, state: dict[str, Any]) -> None:
        path = self._state_path(task_id)
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            shutil.move(tmp, path)
        except Exception as e:
            self.logger.error("Failed to save state: %s", e)

    def _build_context_prompt(self, task_description: str) -> str:
        """Build RUNTIME_CONTEXT + REQUEST_CONFIG + USER_INTENT for the planner; includes hardware and license awareness."""
        try:
            import torch
            has_gpu = torch.cuda.is_available()
        except Exception:
            has_gpu = False
        mat = _get_mat_master_config(self.config)
        crp_cfg = mat.get("crp", {})
        active_licenses = crp_cfg.get("licenses", [])
        task_lower = task_description.lower()
        fidelity = "Screening" if any(w in task_lower for w in ["quick", "fast", "screen", "rough", "粗略", "快速", "筛选"]) else "Production"
        context_data = {
            "RUNTIME_CONTEXT": {
                "Hardware": {
                    "Has_GPU": has_gpu,
                    "Compute_Tier": "HPC_Cluster" if has_gpu else "Local_CPU",
                },
                "License_Keys": active_licenses,
                "Internet_Access": True,
            },
            "REQUEST_CONFIG": {
                "Target_Fidelity": fidelity,
                "Max_Steps": self.max_steps,
            },
            "USER_INTENT": task_description,
        }
        tools_preview = _get_available_tool_names(self.agent)
        tools_str = ", ".join(tools_preview[:100]) if tools_preview else "(none)"
        return f"""# CURRENT RUNTIME STATE (JSON)
{json.dumps(context_data, indent=2, ensure_ascii=False)}

# AVAILABLE TOOLS (use exact names in tool_name)
{tools_str}

# INSTRUCTION
Analyze USER_INTENT against RUNTIME_CONTEXT and REQUEST_CONFIG. Generate the research plan in strict JSON format (plan_id, status, strategy_name, fidelity_level, execution_graph). No other text."""

    def _load_system_prompt(self) -> str:
        """Load planner_system_prompt.txt and append embedded CRP JSON."""
        base = Path(__file__).resolve().parent.parent.parent / "prompts"
        prompt_file = base / "planner_system_prompt.txt"
        if prompt_file.exists():
            raw = prompt_file.read_text(encoding="utf-8")
        else:
            self.logger.warning("planner_system_prompt.txt not found, using minimal fallback")
            raw = "You are a Research Planner. Output a single JSON object with plan_id, status, strategy_name, steps."
        crp_str = json.dumps(INTERNAL_CRP_CONTEXT, indent=2)
        return f"{raw}\n\n# EMBEDDED SYSTEM PROTOCOL (IMMUTABLE)\n{crp_str}"

    def _validate_plan_safety(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Protocol watchdog: block any step mentioning Block_List software."""
        if plan.get("status") == "REFUSED":
            return plan
        block = INTERNAL_CRP_CONTEXT["License_Registry"]["Block_List"]
        for step in plan.get("steps", []):
            text = (step.get("tool_name", "") + " " + step.get("intent", "")).lower()
            for sw in block:
                if sw.lower() in text:
                    msg = f"CRP violation: blocked software '{sw}' in step {step.get('step_id')}."
                    self.logger.warning(msg)
                    return {
                        "plan_id": plan.get("plan_id"),
                        "status": "REFUSED",
                        "refusal_reason": f"{msg} Use {INTERNAL_CRP_CONTEXT['Tool_Stack']['Preferred_DFT']} or {INTERNAL_CRP_CONTEXT['Tool_Stack']['Preferred_MLP']}.",
                        "strategy_name": plan.get("strategy_name"),
                        "steps": plan.get("steps", []),
                    }
        return plan

    def _generate_plan(self, goal: str) -> dict[str, Any]:
        """Produce DEG via LLM with runtime context, normalize to steps, validate against CRP."""
        system = self._load_system_prompt()
        user = self._build_context_prompt(goal)
        dialog = Dialog(
            messages=[SystemMessage(content=system), UserMessage(content=user)],
            tools=[],
        )
        try:
            reply = self.agent.llm.query(dialog)
            raw = _extract_json_from_content(reply.content or "")
            if not raw:
                return {"status": "REFUSED", "refusal_reason": "Planner output contained no valid JSON."}
            plan = json.loads(raw)
        except json.JSONDecodeError as e:
            self.logger.error("Plan JSON parse failed: %s", e)
            return {"status": "REFUSED", "refusal_reason": f"Invalid JSON: {e}"}
        except Exception as e:
            self.logger.error("Plan generation failed: %s", e)
            return {"status": "REFUSED", "refusal_reason": str(e)}
        plan = _normalize_plan(plan, self.max_steps)
        if not plan.get("steps"):
            plan["status"] = "REFUSED"
            plan["refusal_reason"] = plan.get("refusal_reason") or "Plan must have at least one step."
        return self._validate_plan_safety(plan)

    def _revise_plan(self, goal: str, current_plan: dict[str, Any], user_feedback: str) -> dict[str, Any]:
        """Revise plan from user feedback; same schema and validation as _generate_plan."""
        system = self._load_system_prompt()
        external = _plan_to_external_schema(current_plan)
        plan_json = json.dumps(external, ensure_ascii=False, indent=2)
        user = f"REVISION REQUEST\nOriginal goal: {goal}\n\nCurrent plan (JSON):\n{plan_json}\n\nUser feedback: {user_feedback}\n\nOutput the revised plan as a single JSON object (same schema: execution_graph, fidelity_level). No other text."
        dialog = Dialog(
            messages=[SystemMessage(content=system), UserMessage(content=user)],
            tools=[],
        )
        try:
            reply = self.agent.llm.query(dialog)
            raw = _extract_json_from_content(reply.content or "")
            if not raw:
                return {**current_plan, "status": "REFUSED", "refusal_reason": "Revision output contained no valid JSON."}
            plan = json.loads(raw)
        except json.JSONDecodeError as e:
            self.logger.error("Revision JSON parse failed: %s", e)
            return {**current_plan, "status": "REFUSED", "refusal_reason": f"Invalid JSON: {e}"}
        except Exception as e:
            self.logger.error("Plan revision failed: %s", e)
            return {**current_plan, "status": "REFUSED", "refusal_reason": str(e)}
        plan = _normalize_plan(plan, self.max_steps)
        if not plan.get("steps"):
            plan["status"] = "REFUSED"
            plan["refusal_reason"] = plan.get("refusal_reason") or "Plan must have at least one step."
        return self._validate_plan_safety(plan)

    def _ask_human(self, prompt: str) -> str:
        print(f"\033[93m[Planner] {prompt}\033[0m")
        return sys.stdin.readline().strip()

    def run(self, task_description: str, task_id: str = "planner_task") -> dict[str, Any]:
        run_dir = self._run_dir_path()
        workspaces = run_dir / "workspaces" / task_id
        workspaces.mkdir(parents=True, exist_ok=True)
        state = self._load_state(task_id)
        state["goal"] = state.get("goal") or task_description
        state.setdefault("history", [])

        plan = state.get("plan")
        if not _is_deg_plan(plan) or state.get("goal") != task_description:
            self.logger.info("[Planner] Designing flight plan for: %s", task_description[:80])
            plan = self._generate_plan(task_description)
            state["plan"] = plan

        if plan.get("status") == "REFUSED":
            reason = plan.get("refusal_reason", "Unknown")
            self.logger.warning("[CRP] Mission refused: %s", reason)
            return {"status": "failed", "reason": reason, "state": state}

        # Pre-flight: loop until user types 'go' or 'abort'; otherwise treat input as revision feedback
        if self.human_check:
            while True:
                fid = plan.get("fidelity_level", "")
                print(f"\033[92m[Planner] {plan.get('strategy_name')}\033[0m" + (f" (fidelity: {fid})" if fid else ""))
                print("-" * 50)
                for s in plan.get("steps", []):
                    cost = f"[{s.get('compute_cost', '?')}]"
                    print(f"  {s.get('step_id')}. {cost:10} {s.get('tool_name')} -> {s.get('intent')}")
                print("-" * 50)
                ans = self._ask_human("Type 'go' to execute, 'abort' to quit, or describe changes to revise the plan.")
                ans_lower = ans.strip().lower()
                if ans_lower == "go":
                    break
                if ans_lower == "abort":
                    return {"status": "aborted", "state": state}
                if not ans.strip():
                    continue
                self.logger.info("[Planner] Revising plan from user feedback: %s", ans[:100])
                plan = self._revise_plan(task_description, plan, ans)
                state["plan"] = plan
                self._save_state(task_id, state)
                if plan.get("status") == "REFUSED":
                    self.logger.warning("[CRP] Revised plan refused: %s", plan.get("refusal_reason"))
                    return {"status": "failed", "reason": plan.get("refusal_reason"), "state": state}

        solver = DirectSolver(self.agent, self.config)
        if self.run_dir is not None:
            solver.set_run_dir(self.run_dir)

        for step in plan.get("steps", []):
            if step.get("status") == "done":
                continue
            step_id = step.get("step_id", 0)
            tool_name = step.get("tool_name", "")
            intent = step.get("intent", "")
            fallback = step.get("fallback_logic", "None")
            if step.get("requires_human_confirm") or step.get("compute_cost") == "High":
                ans = self._ask_human(f"Step {step_id} is HIGH COST. Proceed? (y/n)")
                if ans.strip().lower() != "y":
                    continue
            self.logger.info("[Planner] Step %s: %s", step_id, tool_name)
            step_dir = workspaces / f"step_{step_id}"
            step_dir.mkdir(parents=True, exist_ok=True)
            solver.set_run_dir(step_dir)
            step_prompt = f"Use tool '{tool_name}' to: {intent}. Fallback: {fallback}"
            try:
                result = solver.run(step_prompt, task_id=f"{task_id}_step_{step_id}")
                step["status"] = "done"
                state["history"].append({"step": step_id, "tool_name": tool_name, "intent": intent[:200], "result_summary": str(result)[:200]})
                self._save_state(task_id, state)
            except Exception as e:
                self.logger.error("[Planner] Step %s failed: %s", step_id, e)
                state["history"].append({"step": step_id, "error": str(e)})
                self._save_state(task_id, state)
        return {"status": "completed", "plan": plan, "state": state}
