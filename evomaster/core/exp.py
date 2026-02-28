"""EvoMaster Core - 基础类和通用流程

提供 Exp 和 Playground 的基础实现，供具体的 playground 继承使用。
"""

import json
import logging
from pathlib import Path
from evomaster.utils.types import TaskInstance
from typing import Any


def extract_agent_response(trajectory: Any) -> str:
    """从轨迹中提取 Agent 的最终回答（模块级工具函数）

    支持两种数据格式：
    - 对象格式（有 .dialogs 属性，来自运行时）
    - dict 格式（JSON 反序列化结果，来自轨迹文件）

    提取优先级：
    1. 最后一条 assistant 消息的 finish tool_call 中的 message 参数
    2. 最后一条有内容的 assistant 消息的 content

    Args:
        trajectory: 执行轨迹（对象或 dict）

    Returns:
        Agent 的回答文本，提取失败返回空字符串
    """
    if not trajectory:
        return ""

    # 获取 dialogs（兼容对象和 dict）
    if isinstance(trajectory, dict):
        dialogs = trajectory.get("dialogs")
    elif hasattr(trajectory, "dialogs"):
        dialogs = trajectory.dialogs
    else:
        return ""

    if not dialogs:
        return ""

    last_dialog = dialogs[-1]

    # 获取 messages（兼容对象和 dict）
    if isinstance(last_dialog, dict):
        messages = last_dialog.get("messages", [])
    else:
        messages = getattr(last_dialog, "messages", [])

    if not messages:
        return ""

    # 反向遍历，找最后一条 assistant 消息
    last_content = ""
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

        # 优先检查 finish tool_call 的 message 参数
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

        # 回退到 content
        if content and content.strip():
            if not last_content:
                last_content = content

    return last_content


class BaseExp:
    """实验基类

    定义单次实验的通用执行逻辑。
    具体 playground 可以继承并覆盖相关方法。
    """

    def __init__(self, agent, config):
        """初始化实验

        Args:
            agent: Agent 实例
            config: EvoMasterConfig 实例
        """
        self.agent = agent
        self.config = config
        self.results = []
        self.logger = logging.getLogger(self.__class__.__name__)
        self.run_dir = None

    @property
    def exp_name(self) -> str:
        """获取 Exp 名称（自动从类名推断）

        例如: SolverExp -> Solver, CriticExp -> Critic
        子类可以覆盖此属性来自定义名称。
        """
        class_name = self.__class__.__name__
        # 移除 "Exp" 后缀
        if class_name.endswith('Exp'):
            return class_name[:-3]
        return class_name

    def set_run_dir(self, run_dir: str | Path) -> None:
        """设置 run 目录

        Args:
            run_dir: Run 目录路径
        """
        self.run_dir = Path(run_dir)

    def run(self, task_description: str, task_id: str = "exp_001", images: list[str] | None = None) -> dict:
        """运行一次实验

        Args:
            task_description: 任务描述
            task_id: 任务 ID
            images: 图片文件路径列表（可选，用于多模态任务）

        Returns:
            运行结果字典
        """
        # 创建任务实例
        task = TaskInstance(
            task_id=task_id,
            task_type="discovery",
            description=task_description,
            images=images or [],
        )

        # 运行 Agent
        self.logger.debug(f"Running task: {task_id}")
        trajectory = self.agent.run(task)

        # 保存结果
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
        """保存实验结果

        Args:
            output_file: 输出文件路径
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
        """从轨迹中提取Agent的最终回答

        Args:
            trajectory: 执行轨迹

        Returns:
            Agent的回答文本
        """
        return extract_agent_response(trajectory)
