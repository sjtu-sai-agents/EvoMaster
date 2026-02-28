"""CLI 入口

python -m evomaster.interface.feishu [--config PATH] [--agent NAME]
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EvoMaster Feishu Bot — 接收飞书消息并执行 playground 任务",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="飞书 Bot 配置文件路径（默认: configs/feishu/config.yaml）",
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="覆盖默认 agent 名称",
    )
    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)

    # 确定项目根目录
    # __main__.py 位于 evomaster/interface/feishu/，project_root 向上 3 级
    project_root = Path(__file__).resolve().parent.parent.parent.parent

    # 加载配置
    config_path = Path(args.config) if args.config else project_root / "configs" / "feishu" / "config.yaml"

    from .config import load_feishu_config

    try:
        config = load_feishu_config(config_path, project_root=project_root)
    except FileNotFoundError as e:
        logger.error("配置文件未找到: %s", e)
        return 1

    # 命令行覆盖
    if args.agent:
        config.default_agent = args.agent

    # 创建 Bot
    from .app import FeishuBot

    bot = FeishuBot(config=config, project_root=project_root)

    # 信号处理
    def _shutdown(signum, _frame):
        logger.info("Received signal %s, shutting down...", signum)
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 启动（阻塞）
    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
