"""Skill Tool - 将 Operator Skill 转换为可执行的 Tool

这个工具允许 Agent 使用 Operator 类型的 Skills。
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from .base import BaseTool, BaseToolParams

if TYPE_CHECKING:
    from evomaster.agent.session import BaseSession
    from evomaster.skills import OperatorSkill, SkillRegistry


class SkillToolParams(BaseToolParams):
    """使用技能并执行相关操作。

    Skill 是 EvoMaster 的扩展能力，包含领域知识和可执行脚本。
    """

    name: ClassVar[str] = "use_skill"

    skill_name: str = Field(description="技能名称")
    action: str = Field(
        description="要执行的操作：'get_info' 获取完整信息，'get_reference' 获取参考文档，'run_script' 运行脚本"
    )
    reference_name: str | None = Field(
        default=None,
        description="参考文档名称（当 action='get_reference' 时需要）"
    )
    script_name: str | None = Field(
        default=None,
        description="脚本名称（当 action='run_script' 时需要）"
    )
    script_args: str | None = Field(
        default=None,
        description="脚本参数，空格分隔（当 action='run_script' 时可选）"
    )


class SkillTool(BaseTool):
    """Skill 工具

    允许 Agent 使用 Operator 类型的 Skills：
    - 获取技能的完整信息（full_info）
    - 获取技能的参考文档
    - 执行技能中的脚本
    """

    name: ClassVar[str] = "use_skill"
    params_class: ClassVar[type[BaseToolParams]] = SkillToolParams

    def __init__(self, skill_registry: SkillRegistry):
        """初始化 SkillTool

        Args:
            skill_registry: SkillRegistry 实例
        """
        super().__init__()
        self.skill_registry = skill_registry

    def execute(self, session: BaseSession, args_json: str) -> tuple[str, dict[str, Any]]:
        """执行技能操作

        Args:
            session: 环境会话
            args_json: 参数 JSON 字符串

        Returns:
            (observation, info) 元组
        """
        try:
            params = self.parse_params(args_json)

            # 获取 skill
            skill = self.skill_registry.get_skill(params.skill_name)
            if skill is None:
                return (
                    f"Error: Skill '{params.skill_name}' not found",
                    {"error": "skill_not_found"}
                )

            # 只支持 Operator 类型的 skill
            from evomaster.skills import OperatorSkill
            if not isinstance(skill, OperatorSkill):
                return (
                    f"Error: Skill '{params.skill_name}' is not an Operator skill",
                    {"error": "invalid_skill_type"}
                )

            self.logger.info(
                "Skill hit: skill_name=%s action=%s ref=%s script=%s",
                params.skill_name,
                params.action,
                params.reference_name or "-",
                params.script_name or "-",
            )

            # 根据 action 执行不同操作
            if params.action == "get_info":
                return self._get_info(skill)
            elif params.action == "get_reference":
                return self._get_reference(skill, params.reference_name)
            elif params.action == "run_script":
                return self._run_script(session, skill, params.script_name, params.script_args)
            else:
                return (
                    f"Error: Unknown action '{params.action}'",
                    {"error": "invalid_action"}
                )

        except Exception as e:
            self.logger.error(f"Skill tool execution failed: {e}", exc_info=True)
            return f"Error: {str(e)}", {"error": str(e)}

    def _get_info(self, skill: OperatorSkill) -> tuple[str, dict[str, Any]]:
        """获取技能的完整信息

        Args:
            skill: OperatorSkill 实例

        Returns:
            (observation, info) 元组
        """
        full_info = skill.get_full_info()
        return (
            f"# Skill: {skill.meta_info.name}\n\n{full_info}",
            {"action": "get_info", "skill_name": skill.meta_info.name}
        )

    def _get_reference(
        self,
        skill: OperatorSkill,
        reference_name: str | None
    ) -> tuple[str, dict[str, Any]]:
        """获取技能的参考文档

        Args:
            skill: OperatorSkill 实例
            reference_name: 参考文档名称

        Returns:
            (observation, info) 元组
        """
        if not reference_name:
            return (
                "Error: reference_name is required for action='get_reference'",
                {"error": "missing_parameter"}
            )

        try:
            reference_content = skill.get_reference(reference_name)
            return (
                f"# Reference: {reference_name}\n\n{reference_content}",
                {
                    "action": "get_reference",
                    "skill_name": skill.meta_info.name,
                    "reference_name": reference_name
                }
            )
        except FileNotFoundError as e:
            return (
                f"Error: {str(e)}",
                {"error": "reference_not_found"}
            )

    def _run_script(
        self,
        session: BaseSession,
        skill: OperatorSkill,
        script_name: str | None,
        script_args: str | None
    ) -> tuple[str, dict[str, Any]]:
        """运行技能中的脚本

        Args:
            session: 环境会话
            skill: OperatorSkill 实例
            script_name: 脚本名称
            script_args: 脚本参数

        Returns:
            (observation, info) 元组
        """
        if not script_name:
            return (
                "Error: script_name is required for action='run_script'",
                {"error": "missing_parameter"}
            )

        # 获取脚本路径
        script_path = skill.get_script_path(script_name)
        if script_path is None:
            available_scripts = ", ".join([s.name for s in skill.available_scripts])
            return (
                f"Error: Script '{script_name}' not found in skill '{skill.meta_info.name}'. "
                f"Available scripts: {available_scripts}",
                {"error": "script_not_found"}
            )
        # 转换为绝对路径
        script_path = script_path.resolve()
        # 构建命令
        if script_path.suffix == '.py':
            cmd = f"python {script_path}"
        elif script_path.suffix == '.sh':
            cmd = f"bash {script_path}"
        elif script_path.suffix == '.js':
            cmd = f"node {script_path}"
        else:
            return (
                f"Error: Unsupported script type: {script_path.suffix}",
                {"error": "unsupported_script_type"}
            )

        # 添加参数
        if script_args:
            cmd += f" {script_args}"

        # 使用 session 的 bash 工具执行脚本
        try:
            result = session.exec_bash(cmd)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exit_code", 0)

            output = f"Script output:\n{stdout}"
            if stderr:
                output += f"\n\nStderr:\n{stderr}"
            if exit_code != 0:
                output += f"\n\nExit code: {exit_code}"

            return (
                output,
                {
                    "action": "run_script",
                    "skill_name": skill.meta_info.name,
                    "script_name": script_name,
                    "script_args": script_args,
                    "exit_code": exit_code,
                }
            )
        except Exception as e:
            return (
                f"Error executing script: {str(e)}",
                {"error": "script_execution_failed"}
            )
