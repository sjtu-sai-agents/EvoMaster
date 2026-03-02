"""运行相关的通用工具：代码提取、agent 回复提取、模拟工具调用执行代码"""

import re
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function

from evomaster.agent.tools.builtin.bash import BashTool


def extract_python_code(text: str) -> str:
    """从带 Markdown 的回复中提取首个 Python 代码块；若无则返回原文"""
    if not text:
        return ""
    m = re.search(r"```(?:python|py)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def extract_json_code(text: str) -> str:
    """从带 Markdown 的回复中提取首个 JSON 代码块；若无则返回原文"""
    if not text:
        return ""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def extract_agent_response(trajectory: Any) -> str:
    """抽取 Agent 轨迹中最后一assistant 文本"""
    if not trajectory or not getattr(trajectory, "dialogs", None):
        return ""
    last_dialog = trajectory.dialogs[-1]
    for msg in reversed(last_dialog.messages):
        if hasattr(msg, "role") and msg.role.value == "assistant":
            if getattr(msg, "content", None):
                return msg.content
    return ""


def run_code_via_bash(agent, workspace: Path, code: str, node_id: str) -> dict[str, Any]:
    """通过模拟 OpenAI 工具调用执行代码，确保链路经agent->session"""
    workspace.mkdir(parents=True, exist_ok=True)
    script = workspace / f"solution_{node_id}.py"
    script.write_text(code, encoding="utf-8")

    tool_call = ChatCompletionMessageToolCall(
        id=f"call_{node_id}",
        type="function",
        function=Function(
            name=BashTool.name,
            arguments=(
                f'{{"command": "cd {workspace} && python {script.name}", "is_input": "false", "timeout": "{-1}"}}'
            ),
        ),
    )
    obs, info = agent._execute_tool(tool_call)

    return {
        "stdout": obs,
        "exit_code": info.get("exit_code", -1),
        "working_dir": info.get("working_dir"),
        "script": str(script),
    }

# Helper to extract natural language plan before first code block
def extract_text_up_to_code(text: str) -> str:
    """提取首个代码块前的自然语言文本 """
    if not text:
        return ""
    if "```" not in text:
        return text.strip()
    return text.split("```", 1)[0].strip()
