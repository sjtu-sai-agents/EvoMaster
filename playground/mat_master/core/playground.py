"""Mat Master Playground 实现

材料科学 / 计算材料方向的 EvoMaster agent，接入 Mat 的 MCP 工具
（Structure Generator、Science Navigator、Document Parser、DPA Calculator）。
"""

import logging
from pathlib import Path

from evomaster.core import BasePlayground, register_playground


@register_playground("mat_master")
class MatMasterPlayground(BasePlayground):
    """Mat Master Playground

    材料科学向的 playground，使用 Mat 的 MCP 服务（结构生成、科学导航、
    文档解析、DPA 计算），支持 LiteLLM 与 Azure 的 LLM 配置格式。

    使用方式：
        python run.py --agent mat_master --task "材料相关任务"
    """

    def __init__(self, config_dir: Path = None, config_path: Path = None):
        """初始化 MatMasterPlayground

        Args:
            config_dir: 配置目录路径，默认为 configs/mat_master/
            config_path: 配置文件完整路径（如果提供，会覆盖 config_dir）
        """
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "mat_master"

        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
