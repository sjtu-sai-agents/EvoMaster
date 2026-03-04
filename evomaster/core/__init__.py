"""EvoMaster Core - 通用基础类

提供 Exp 和 Playground 的基础实现，用于快速构建具体的 playground。

使用示例：
    from evomaster.core import BasePlayground, BaseExp

    # 直接使用（最简单）
    playground = BasePlayground()
    result = playground.run("发现规律")

    # 自定义 Exp
    class MyExp(BaseExp):
        def run(self, task_description, task_id="exp_001"):
            # 自定义逻辑
            return super().run(task_description, task_id)

    # 自定义 Playground
    class MyPlayground(BasePlayground):
        def _create_exp(self):
            return MyExp(self.agent, self.config)

    playground = MyPlayground()
    result = playground.run("发现规律")
"""

from .exp import BaseExp, extract_agent_response
from .playground import BasePlayground
from .registry import (
    register_playground,
    get_playground_class,
    list_registered_playgrounds,
    get_registry_info,
)

__all__ = [
    "BaseExp",
    "BasePlayground",
    "extract_agent_response",
    "register_playground",
    "get_playground_class",
    "list_registered_playgrounds",
    "get_registry_info",
]
