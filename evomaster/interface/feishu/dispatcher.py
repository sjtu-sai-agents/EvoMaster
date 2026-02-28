"""任务调度器

将飞书消息分发到线程池，复用 playground 基础设施执行任务。
"""

from __future__ import annotations

import importlib
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_playgrounds_imported = False


def _ensure_playgrounds_imported(project_root: Path) -> None:
    """确保所有 playground 模块已导入（触发 @register_playground 装饰器）

    复用 run.py:auto_import_playgrounds() 的逻辑。
    """
    global _playgrounds_imported
    if _playgrounds_imported:
        return

    # 确保 project_root 在 sys.path 中
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    playground_dir = project_root / "playground"
    if not playground_dir.exists():
        logger.warning("Playground directory not found: %s", playground_dir)
        _playgrounds_imported = True
        return

    imported_count = 0
    for agent_dir in playground_dir.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
            continue

        module_name = f"playground.{agent_dir.name}.core.playground"
        try:
            importlib.import_module(module_name)
            logger.info("Imported playground: %s", module_name)
            imported_count += 1
        except ImportError as e:
            logger.warning("Failed to import %s: %s", module_name, e)
        except Exception as e:
            logger.warning("Error importing %s: %s", module_name, e)

    logger.info("Auto-imported %d playground modules", imported_count)
    _playgrounds_imported = True


def _extract_final_answer(result: dict[str, Any]) -> str:
    """从 playground 执行结果中提取最终回答

    Args:
        result: playground.run() 返回的结果字典

    Returns:
        最终回答文本
    """
    from evomaster.core import extract_agent_response

    trajectory = result.get("trajectory")
    if not trajectory:
        error = result.get("error", "")
        if error:
            return f"任务执行失败: {error}"
        return f"任务完成，状态: {result.get('status', 'unknown')}"

    answer = extract_agent_response(trajectory)
    if answer:
        return answer

    status = result.get("status", "unknown")
    steps = result.get("steps", 0)
    return f"任务完成（状态: {status}，步骤: {steps}），但未提取到文本回答。"


class TaskDispatcher:
    """任务调度器：将消息分发到线程池执行 playground 任务"""

    def __init__(
        self,
        project_root: Path,
        default_agent: str = "minimal",
        default_config_path: Optional[str] = None,
        max_workers: int = 4,
        task_timeout: int = 600,
        on_result: Optional[Callable[[str, str, str], None]] = None,
    ):
        """
        Args:
            project_root: 项目根目录
            default_agent: 默认 agent 名称
            default_config_path: 默认配置文件路径（相对于 project_root）
            max_workers: 最大并发线程数
            task_timeout: 任务超时（秒）
            on_result: 结果回调 (chat_id, message_id, result_text) -> None
        """
        self._project_root = project_root
        self._default_agent = default_agent
        self._default_config_path = default_config_path
        self._task_timeout = task_timeout
        self._on_result = on_result
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="feishu-task",
        )
        self._active_tasks: dict[str, Any] = {}

        # 预加载 playgrounds
        _ensure_playgrounds_imported(project_root)

    def dispatch(
        self,
        chat_id: str,
        message_id: str,
        task_text: str,
        agent_name: Optional[str] = None,
    ) -> None:
        """提交任务到线程池

        Args:
            chat_id: 聊天 ID
            message_id: 消息 ID（用于回复）
            task_text: 任务描述
            agent_name: 指定 agent 名称，None 使用默认值
        """
        agent = agent_name or self._default_agent
        future = self._executor.submit(
            self._run_task, chat_id, message_id, task_text, agent
        )
        self._active_tasks[message_id] = future
        future.add_done_callback(lambda f: self._on_task_done(f, chat_id, message_id))

        # 超时守护线程
        def _timeout_guard():
            try:
                future.result(timeout=self._task_timeout)
            except TimeoutError:
                logger.warning(
                    "Task timed out: message_id=%s, timeout=%ds",
                    message_id,
                    self._task_timeout,
                )
                future.cancel()
            except Exception:
                pass  # 正常完成或异常，由 _on_task_done 处理

        threading.Thread(
            target=_timeout_guard,
            daemon=True,
            name=f"timeout-{message_id[:8]}",
        ).start()

    def _run_task(
        self,
        chat_id: str,
        message_id: str,
        task_text: str,
        agent_name: str,
    ) -> str:
        """在后台线程中执行 playground 任务

        Returns:
            结果文本
        """
        from evomaster.core import get_playground_class

        # 确定配置路径
        if self._default_config_path:
            config_path = self._project_root / self._default_config_path
        else:
            config_path = self._project_root / "configs" / agent_name / "config.yaml"

        if not config_path.exists():
            return f"配置文件不存在: {config_path}"

        # 创建 run 目录（微秒精度 + message_id 后缀防碰撞）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        short_id = message_id[-6:] if len(message_id) > 6 else message_id
        run_dir = self._project_root / "runs" / f"feishu_{agent_name}_{timestamp}_{short_id}"

        task_id = f"feishu_{message_id}"

        try:
            logger.info(
                "Starting task: agent=%s, task_id=%s, text=%s",
                agent_name,
                task_id,
                task_text[:100],
            )

            playground = get_playground_class(agent_name, config_path=config_path)
            playground.set_run_dir(run_dir, task_id=task_id)
            result = playground.run(task_description=task_text)

            answer = _extract_final_answer(result)
            logger.info("Task completed: task_id=%s, status=%s", task_id, result.get("status"))
            return answer

        except Exception as e:
            logger.exception("Task failed: task_id=%s", task_id)
            return f"任务执行出错: {e}"

    def _on_task_done(self, future, chat_id: str, message_id: str) -> None:
        """任务完成回调"""
        self._active_tasks.pop(message_id, None)

        try:
            result_text = future.result(timeout=0)
        except TimeoutError:
            result_text = f"任务超时（超过 {self._task_timeout} 秒）"
        except Exception as e:
            result_text = f"任务执行异常: {e}"

        if self._on_result:
            try:
                self._on_result(chat_id, message_id, result_text)
            except Exception:
                logger.exception("Error in on_result callback")

    def shutdown(self, wait: bool = True) -> None:
        """关闭线程池"""
        logger.info("Shutting down task dispatcher...")
        self._executor.shutdown(wait=wait)
        logger.info("Task dispatcher shut down")
