#!/usr/bin/env python3
"""EvoMaster 统一入口

使用方式：
  python run.py --agent minimal --task "你的任务描述"
  python run.py --agent agent-builder --config configs/agent-builder/config.yaml
  python run.py --agent mcp-example --interactive

参数说明：
  --agent: 指定 playground 名称（必需）
  --config: 指定配置文件路径（可选，默认使用 configs/{agent}/config.yaml）
  --task: 任务描述（可选，如不提供则进入交互式输入）
  --interactive: 交互式模式（可选）
  --run-dir: 指定 run 目录（可选，默认自动创建 runs/{agent}_{timestamp}/）
"""

import argparse
import logging
import sys
import importlib
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evomaster.core import get_playground_class, list_registered_playgrounds


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="EvoMaster 统一入口 - 运行指定的 playground agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用默认配置运行 minimal agent
  python run.py --agent minimal --task "分析数据"

  # 使用自定义配置
  python run.py --agent minimal --config my_config.yaml --task "分析数据"

  # 交互式模式
  python run.py --agent agent-builder --interactive

  # 指定 run 目录
  python run.py --agent minimal --task "分析数据" --run-dir runs/my_experiment

  # 批量任务（串行）
  python run.py --agent minimal --task-file tasks.json

  # 批量任务（并行）
  python run.py --agent minimal --task-file tasks.json --parallel
        """
    )

    parser.add_argument(
        "--agent",
        required=True,
        help="Playground agent 名称（如 minimal, agent-builder, mcp-example）"
    )

    parser.add_argument(
        "--config",
        help="配置文件路径（默认：configs/{agent}/config.yaml）"
    )

    # 任务输入（互斥）
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument(
        "--task",
        help="单个任务描述，或任务文件路径（.txt 或 .md）"
    )
    task_group.add_argument(
        "--task-file",
        help="包含多个任务的 JSON 文件路径"
    )
    task_group.add_argument(
        "--interactive",
        action="store_true",
        help="交互式模式（手动输入任务）"
    )

    parser.add_argument(
        "--run-dir",
        help="指定 run 目录（默认自动创建 runs/{agent}_{timestamp}/）"
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="并行执行多个任务（仅在使用 --task-file 时有效）"
    )

    return parser.parse_args()


def setup_logging():
    """配置基础日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 禁用 httpx 的 INFO 级别日志（只保留 WARNING 及以上）
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_task_description(args):
    """获取任务描述
    
    如果 args.task 是文件路径（.txt 或 .md），则读取文件内容；
    否则直接返回 args.task 作为任务描述。
    """
    if args.task:
        task_path = Path(args.task)
        # 检查是否是文件路径（.txt 或 .md）
        if task_path.suffix.lower() in ['.txt', '.md'] and task_path.exists() and task_path.is_file():
            try:
                with open(task_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if not content:
                    print(f"❌ 错误：文件 {task_path} 为空")
                    sys.exit(1)
                return content
            except Exception as e:
                print(f"❌ 错误：读取文件 {task_path} 失败: {e}")
                sys.exit(1)
        # 不是文件路径或文件不存在，直接作为任务描述返回
        return args.task

    if args.interactive:
        print("\n" + "=" * 60)
        print("📝 请输入任务描述（输入空行结束）：")
        print("=" * 60)
        lines = []
        while True:
            try:
                line = input()
                if not line.strip():
                    break
                lines.append(line)
            except EOFError:
                break

        if not lines:
            print("❌ 错误：未提供任务描述")
            sys.exit(1)

        return '\n'.join(lines)

    # 既没有 --task 也没有 --interactive
    print("❌ 错误：请使用 --task 提供任务描述或使用 --interactive 进入交互式模式")
    sys.exit(1)


def parse_task_file(task_file_path: Path):
    """解析任务 JSON 文件

    Args:
        task_file_path: JSON 文件路径

    Returns:
        任务列表，每个任务包含 {id, description} 字段
    """
    import json

    with open(task_file_path, 'r', encoding='utf-8') as f:
        tasks_raw = json.load(f)

    if not isinstance(tasks_raw, list):
        raise ValueError(f"任务文件格式错误：期望列表，实际为 {type(tasks_raw).__name__}")

    tasks = []
    for idx, task in enumerate(tasks_raw):
        if isinstance(task, str):
            # 兼容简单列表格式：["任务1", "任务2"]
            task_obj = {"description": task}
        elif isinstance(task, dict):
            task_obj = task.copy()
        else:
            raise ValueError(f"任务 {idx} 格式错误：期望字符串或字典，实际为 {type(task).__name__}")

        # 自动生成 ID（如果没有）
        if "id" not in task_obj:
            task_obj["id"] = f"task_{idx}"

        # 验证必需字段
        if "description" not in task_obj:
            raise ValueError(f"任务 {idx} 缺少必需字段 'description'")

        tasks.append(task_obj)

    return tasks


def run_single_task(agent_name: str, config_path: Path, run_dir: Path,
                    task_id: str, task_description: str):
    """运行单个任务（在主进程中）

    注意：这个函数在主进程中运行，不是在独立进程中。
    每个任务有独立的 workspace，通过 task_id 区分。

    Args:
        agent_name: Agent 名称
        config_path: 配置文件路径
        run_dir: 运行目录
        task_id: 任务 ID
        task_description: 任务描述

    Returns:
        任务结果字典
    """
    logger = logging.getLogger(__name__)

    try:
        # 加载 Playground
        playground = get_playground_class(agent_name, config_path=config_path)

        # 设置 run_dir 和 task_id（会创建独立的 workspace）
        playground.set_run_dir(run_dir, task_id=task_id)

        # 运行任务
        result = playground.run(task_description=task_description)
        result["task_id"] = task_id

        logger.info(f"✅ Task {task_id} completed: {result['status']}")
        return result

    except Exception as e:
        logger.error(f"❌ Task {task_id} failed: {e}", exc_info=True)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "steps": 0
        }


def run_tasks_sequential(agent_name: str, config_path: Path, run_dir: Path,
                         tasks: list):
    """串行运行多个任务

    Args:
        agent_name: Agent 名称
        config_path: 配置文件路径
        run_dir: 运行目录
        tasks: 任务列表

    Returns:
        所有任务的结果列表
    """
    results = []
    for task in tasks:
        result = run_single_task(
            agent_name,
            config_path,
            run_dir,
            task["id"],
            task["description"]
        )
        results.append(result)
    return results


def run_tasks_parallel(agent_name: str, config_path: Path, run_dir: Path,
                       tasks: list, max_workers: int = 4):
    """并行运行多个任务

    使用 ProcessPoolExecutor 并行执行任务。

    Args:
        agent_name: Agent 名称
        config_path: 配置文件路径
        run_dir: 运行目录
        tasks: 任务列表
        max_workers: 最大并行进程数

    Returns:
        所有任务的结果列表
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    logger = logging.getLogger(__name__)
    results = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_task = {
            executor.submit(
                run_single_task,
                agent_name,
                config_path,
                run_dir,
                task["id"],
                task["description"]
            ): task
            for task in tasks
        }

        # 收集结果
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Task {task['id']} failed: {e}")
                results.append({
                    "task_id": task["id"],
                    "status": "failed",
                    "error": str(e),
                    "steps": 0
                })

    return results



def auto_import_playgrounds():
    """自动导入所有 playground 模块以触发装饰器注册

    遍历 playground 目录下的所有 agent 子目录，尝试导入其 core.playground 模块。
    这样可以确保所有使用 @register_playground 装饰器的类都被注册。
    """
    logger = logging.getLogger(__name__)
    playground_dir = project_root / "playground"

    if not playground_dir.exists():
        logger.warning(f"Playground 目录不存在: {playground_dir}")
        return

    imported_count = 0
    for agent_dir in playground_dir.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith('_'):
            continue

        # 尝试导入 playground.{agent}.core.playground
        # 注意：目录名可以包含连字符，importlib 可以直接导入
        module_name = f"playground.{agent_dir.name}.core.playground"
        try:
            importlib.import_module(module_name)
            logger.info(f"✅ Successfully imported {module_name}")
            imported_count += 1
        except ImportError as e:
            # 如果没有 core/playground.py，跳过（agent 可能使用默认 BasePlayground）
            # 但如果是其他导入错误（如缺少依赖），应该警告
            error_msg = str(e)
            if "No module named" in error_msg or "cannot import name" in error_msg or "core.playground" not in error_msg:
                logger.warning(f"❌ Failed to import {module_name}: {e}", exc_info=True)
            else:
                logger.debug(f"No custom playground for '{agent_dir.name}': {e}")
        except Exception as e:
            # 其他错误（语法错误等）应该警告
            logger.warning(f"❌ Failed to import {module_name}: {e}", exc_info=True)

    logger.info(f"Auto-imported {imported_count} playground modules")


def main():
    """主入口函数"""
    setup_logging()
    logger = logging.getLogger(__name__)

    # 自动导入所有 playground 模块（触发装饰器注册）
    auto_import_playgrounds()

    # 调试：显示已注册的 playground
    registered = list_registered_playgrounds()
    if registered:
        logger.debug(f"Registered playgrounds: {registered}")

    args = parse_args()

    # 1. 确定配置文件路径
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = project_root / "configs" / args.agent / "config.yaml"

    if not config_path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        sys.exit(1)

    # 2. 确定 run 目录
    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = project_root / "runs" / f"{args.agent}_{timestamp}"

    # 3. 解析任务
    if args.task_file:
        # 批量任务模式
        task_file = Path(args.task_file)
        if not task_file.exists():
            logger.error(f"任务文件不存在: {task_file}")
            sys.exit(1)

        try:
            tasks = parse_task_file(task_file)
            logger.info(f"📋 加载了 {len(tasks)} 个任务")
        except Exception as e:
            logger.error(f"解析任务文件失败: {e}")
            sys.exit(1)
    else:
        # 单任务模式
        task_description = get_task_description(args)
        tasks = [{
            "id": "task_0",
            "description": task_description
        }]

    # 4. 打印运行信息
    logger.info("=" * 60)
    logger.info("🚀 EvoMaster 启动")
    logger.info("=" * 60)
    logger.info(f"Agent: {args.agent}")
    logger.info(f"Config: {config_path}")
    logger.info(f"Run Directory: {run_dir}")
    logger.info(f"Tasks: {len(tasks)}")
    if len(tasks) > 1:
        mode = "并行" if args.parallel else "串行"
        logger.info(f"执行模式: {mode}")
    logger.info("=" * 60)

    # 5. 运行任务
    try:
        if len(tasks) > 1 and args.parallel:
            # 并行模式
            logger.info("🔄 并行执行任务...")
            results = run_tasks_parallel(args.agent, config_path, run_dir, tasks)
        else:
            # 串行模式（包括单任务）
            if len(tasks) > 1:
                logger.info("🔄 串行执行任务...")
            results = run_tasks_sequential(args.agent, config_path, run_dir, tasks)

        # 6. 输出结果
        logger.info("=" * 60)
        logger.info("✅ 所有任务完成")
        logger.info("=" * 60)

        # 统计结果（注意：trajectory.status 的值是 "completed"/"failed"/"cancelled"）
        success_count = sum(1 for r in results if r.get('status') == 'completed')
        failed_count = len(results) - success_count

        if len(tasks) == 1:
            # 单任务模式：显示详细结果
            result = results[0]
            logger.info(f"状态: {result['status']}")
            logger.info(f"步数: {result.get('steps', 0)}")
        else:
            # 批量任务模式：显示汇总和每个任务状态
            logger.info(f"成功: {success_count}/{len(results)}")
            logger.info(f"失败: {failed_count}/{len(results)}")
            logger.info("")
            logger.info("任务状态:")
            for result in results:
                status_icon = "✅" if result.get('status') == 'completed' else "❌"
                logger.info(f"  {status_icon} {result['task_id']}: {result['status']} ({result.get('steps', 0)} steps)")

        logger.info("")
        logger.info(f"结果目录: {run_dir}")
        logger.info(f"  - 配置: {run_dir}/config.yaml")
        logger.info(f"  - 日志: {run_dir}/logs/")
        logger.info(f"  - 轨迹: {run_dir}/trajectories/")
        if len(tasks) > 1:
            logger.info(f"  - Workspaces: {run_dir}/workspaces/")
        else:
            logger.info(f"  - Workspace: {run_dir}/workspace/")
        logger.info("=" * 60)

        return 0 if failed_count == 0 else 1

    except Exception as e:
        logger.error(f"运行失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
