"""ml-master 的 UCT 工具模块。

用途：在 EvoMaster 中复用 ML-Master 的 UCT 搜索逻辑，供调试/改进/评分流程调用。
核心功能：
- 解析执行结果得到验证指标（通常由 LLM 解析器完成）
- 更新节点奖励与 UCT 分数
- 选择下一轮要扩展的节点

快速示例（伪代码）：
    from playground.ml_master1.core.uct import (
        MetricReview, UCTDecayConfig, UCTSearchConfig, UCTSearchManager
    )
    mgr = UCTSearchManager(UCTSearchConfig(), UCTDecayConfig())
    root = mgr.root
    node = mgr.create_child(root, stage="draft", plan="baseline", code="...")
    review = MetricReview(metric=0.82, lower_is_better=False, summary="val acc=0.82")
    mgr.ingest_result(node, review)
    next_node = mgr.select_next()
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

StageLiteral = Literal["root", "draft", "debug", "improve"]


# --------------------------------------------------------------------------- #
# 指标处理
# --------------------------------------------------------------------------- #


@dataclass
class MetricReview:
    """外部解析器/LLM 返回的标准化度量结果。

    Args:
        metric: 验证指标值（None 表示缺失或失败）。
        lower_is_better: 若为 True 则代表越小越好，会反转 maximize。
        maximize: 是否越大越好（默认 True）。
        is_bug: 解析认定是否有 bug。
        has_submission: 是否生成了提交文件。
        summary: 对执行结果的简述。
        raw_output: 原始解析文本（可选）。
    """

    metric: Optional[float]
    lower_is_better: Optional[bool] = None
    maximize: bool = True
    is_bug: bool = False
    has_submission: bool = True
    summary: str = ""
    raw_output: Optional[str] = None

    def __post_init__(self) -> None:
        if self.lower_is_better is not None:
            self.maximize = not self.lower_is_better
        if self.metric is not None:
            self.metric = float(self.metric)


@dataclass
class MetricValue:
    """可比较的指标包装，供 UCT 打分使用。"""

    value: Optional[float]
    maximize: bool = True

    def __post_init__(self) -> None:
        if self.value is not None:
            self.value = float(self.value)

    def __gt__(self, other: "MetricValue") -> bool:  # type: ignore[override]
        if self.value is None:
            return False
        if other.value is None:
            return True
        if self.value == other.value:
            return False
        comp = self.value > other.value
        return comp if self.maximize else not comp


class WorstMetricValue(MetricValue):
    """表示最差值（bug/无效）。"""

    def __init__(self) -> None:
        super().__init__(value=None, maximize=True)


# --------------------------------------------------------------------------- #
# 搜索与衰减配置
# --------------------------------------------------------------------------- #


@dataclass
class UCTSearchConfig:
    """搜索超参（与 ML-Master 保持一致）。"""

    back_debug_depth: int = 3
    max_debug_depth: int = 20
    num_drafts: int = 5
    num_bugs: int = 1
    num_improves: int = 3
    invalid_metric_upper_bound: int = 100
    metric_improvement_threshold: float = 0.0001
    max_improve_failure: int = 3


@dataclass
class UCTDecayConfig:
    """探索系数衰减配置。"""

    decay_type: Literal[
        "constant",
        "linear",
        "exponential",
        "piecewise",
        "dynamic_piecewise",
    ] = "piecewise"
    exploration_constant: float = 1.414
    lower_bound: float = 0.5

    # 线性衰减
    linear_alpha: float = 0.01
    # 指数衰减
    exponential_gamma: float = 0.99
    # 分段衰减
    piecewise_alpha: float = 0.01
    piecewise_phase_ratios: tuple[float, float] = (0.3, 0.7)
    # 动态分段衰减
    dynamic_alpha: float = 0.01
    dynamic_phase_ratios: tuple[float, float] = (0.85, 1.0)


def _linear_decay(t: int, initial_c: float, alpha: float, lower_bound: float) -> float:
    """线性衰减。

    Args:
        t: 当前步数
        initial_c: 初始探索系数
        alpha: 衰减斜率
        lower_bound: 下限
    Returns:
        衰减后的探索系数
    """
    return max(initial_c - alpha * t, lower_bound)


def _exponential_decay(
    t: int, initial_c: float, gamma: float, lower_bound: float
) -> float:
    """指数衰减。

    Args:
        t: 当前步数
        initial_c: 初始探索系数
        gamma: 衰减系数
        lower_bound: 下限
    Returns:
        衰减后的探索系数
    """
    return max(initial_c * (gamma**t), lower_bound)


def _piecewise_decay(
    t: int,
    initial_c: float,
    t1: int,
    t2: int,
    alpha: float,
    lower_bound: float,
) -> float:
    """分段线性衰减。

    Args:
        t: 当前步数
        initial_c: 初始探索系数
        t1: 第一阶段结束步数
        t2: 第二阶段结束步数
        alpha: 第二阶段斜率
        lower_bound: 下限
    Returns:
        衰减后的探索系数
    """
    if t < t1:
        return initial_c
    if t <= t2:
        return max(initial_c - alpha * (t - t1), lower_bound)
    return lower_bound


def _dynamic_piecewise_decay(
    steps_limit: int,
    n_nodes: int,
    initial_c: float,
    start_time: float,
    time_limit: float,
    alpha: float,
    lower_bound: float,
    phase_ratios: tuple[float, float],
) -> float:
    """动态分段衰减，根据时间/进度估算。

    Args:
        steps_limit: 计划最大节点数
        n_nodes: 已生成节点数
        initial_c: 初始探索系数
        start_time: 搜索起始时间戳
        time_limit: 总时间限制
        alpha: 衰减斜率
        lower_bound: 下限
        phase_ratios: 两阶段分界比例
    Returns:
        衰减后的探索系数
    """
    now = time.time()
    elapsed = now - start_time
    remaining = max(time_limit - elapsed, 1e-5)

    speed = n_nodes / elapsed if elapsed > 0 else 1.0
    n_remaining = round(speed * remaining)
    estimated_total = min(n_nodes + n_remaining, steps_limit)
    progress = n_nodes / estimated_total if estimated_total > 0 else 0.0

    p1, p2 = phase_ratios
    if progress < p1:
        return initial_c
    if progress < p2:
        decay_length = p2 - p1
        decay_progress = (progress - p1) / decay_length if decay_length > 0 else 0
        c_val = initial_c - alpha * decay_progress * estimated_total
        return max(c_val, lower_bound)
    return lower_bound


# --------------------------------------------------------------------------- #
# 节点表示
# --------------------------------------------------------------------------- #


@dataclass(eq=False)
class UCTNode:
    """UCT 树节点，记录计划/代码/奖励/子节点等状态。"""

    stage: StageLiteral
    plan: str = ""
    code: str = ""
    stdout: Optional[str] = None  # 追加：保存最近一次执行的输出，便于调试
    exit_code: Optional[int] = None  # 追加：保存最近一次执行的退出码
    parent: Optional["UCTNode"] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    # 执行信息与元数据
    analysis: Optional[str] = None
    metric: MetricValue = field(default_factory=WorstMetricValue)
    is_buggy: Optional[bool] = None
    is_valid: Optional[bool] = None
    is_terminal: bool = False
    finish_time: Optional[float] = None
    is_debug_success: bool = False
    continue_improve: bool = False
    improve_failure_depth: int = 0
    local_best_node: Optional["UCTNode"] = None

    # 树统计
    visits: int = 0
    total_reward: float = 0.0
    children: set["UCTNode"] = field(default_factory=set)
    expected_child_count: int = 0
    locked: bool = False
    # Track first-time stats for logging/debugging.
    initial_reward: float | None = None
    initial_total_reward: float | None = None
    initial_visits: int | None = None
    initial_uct: float | None = None

    def __post_init__(self) -> None:
        if self.parent is not None:
            self.parent.children.add(self)

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def num_children(self) -> int:
        return len(self.children)

    @property
    def debug_depth(self) -> int:
        if self.stage != "debug" or self.parent is None:
            return 0
        return 1 + self.parent.debug_depth

    def expect_child(self) -> None:
        self.expected_child_count += 1

    def complete_child(self) -> None:
        self.expected_child_count = max(self.expected_child_count - 1, 0)

    def is_fully_expanded(self, cfg: UCTSearchConfig) -> bool:
        if self.stage == "root":
            return self.expected_child_count >= cfg.num_drafts
        if self.is_buggy:
            if self._has_non_bug_child():
                return True
            return self.expected_child_count >= cfg.num_bugs
        return self.expected_child_count >= cfg.num_improves

    def _has_non_bug_child(self) -> bool:
        return any(child.is_buggy is False for child in self.children)

    def uct_value(self, exploration_constant: float, parent_visits: int) -> float:
        if self.visits == 0:
            return float("inf")
        parent_total = max(parent_visits, 1)
        exploitation = self.total_reward / self.visits
        exploration = exploration_constant * math.sqrt(math.log(parent_total) / self.visits)
        return exploitation + exploration

    def update_reward(self, reward: float) -> None:
        self.visits += 1
        self.total_reward += reward

    def fetch_child_memory(self, include_code: bool = False) -> str:
        """Summarize child nodes for prompt Memory (ported from ML-Master MCTSNode)."""
        logger.info("fetch_child_memory")
        summary: list[str] = []
        for child in self.children:
            if child.is_buggy is None:
                continue
            part = f"Design: {child.plan}\n"
            if include_code:
                part += f"Code: {child.code}\n"
            if child.is_buggy:
                part += "Results: The implementation of this design has bugs.\n"
                part += "Insight: Using a different approach may not result in the same bugs as the above approach.\n"
            else:
                if child.analysis:
                    part += f"Results: {child.analysis}\n"
                if child.metric:
                    part += f"Validation Metric: {child.metric.value}\n"
            summary.append(part)
        if not summary:
            summary.append("There is no previous memory")
        return "\n-------------------------------\n".join(summary)

    def fetch_parent_memory(self, include_code: bool = False) -> str:
        """Summarize parent when it is a successful node."""
        logger.info("fetch_parent_memory")
        if self.parent and self.parent.is_buggy is False:
            part = f"Design: {self.parent.plan}\n"
            if include_code:
                part += f"Code: {self.parent.code}\n"
            if self.parent.analysis:
                part += f"Results: {self.parent.analysis}\n"
            if self.parent.metric:
                part += f"Validation Metric: {self.parent.metric.value}\n"
            return part
        return ""


# --------------------------------------------------------------------------- #
# 搜索管理器
# --------------------------------------------------------------------------- #

MetricParser = Callable[[str, str, Optional[str]], MetricReview]


class UCTSearchManager:
    """UCT 状态管理器，复刻 ML-Master 的 select/backprop 流程。"""

    def __init__(
        self,
        search_cfg: UCTSearchConfig,
        decay_cfg: UCTDecayConfig,
        *,
        time_limit: float = 0,
        grader: Optional[Callable[[str, Path], Tuple[bool, dict | str]]] = None,
        exp_id: Optional[str] = None,
        submission_dir: Optional[Path | str] = None,
    ) -> None:
        self.search_cfg = search_cfg
        self.decay_cfg = decay_cfg
        self.time_limit = time_limit
        self.grader = grader
        self.exp_id = exp_id
        self.submission_dir = Path(submission_dir) if submission_dir else None
        # Optional snapshot callback: fn(node, submission_path, review, reward) -> None
        self.snapshot_fn: Optional[Callable[[UCTNode, Optional[Path], MetricReview, float], None]] = None

        self.root = UCTNode(stage="root", plan="virtual root", code="")
        self.best_node: Optional[UCTNode] = None
        self.best_metric: Optional[float] = None

        self.current_step: int = 0
        self.search_start_time = time.time()

    # ---- 对外 API ----------------------------------------------------- #

    def create_child(
        self,
        parent: UCTNode,
        stage: StageLiteral,
        plan: str = "",
        code: str = "",
    ) -> UCTNode:
        """创建子节点并增加父节点预期子数量。

        Args:
            parent: 父节点
            stage: 节点阶段（root/draft/debug/improve）
            plan: 方案描述
            code: 生成的代码
        Returns:
            新建的子节点
        """
        parent.expect_child()
        node = UCTNode(stage=stage, plan=plan, code=code, parent=parent)
        logger.info(f"Created child node {node.id} stage={stage} parent={parent.id if parent else None} plan={plan[:80]!r}")
        return node

    def select_next(self, node: Optional[UCTNode] = None) -> UCTNode:
        """基于 UCT 的节点选择。

        Args:
            node: 可选，起始节点；默认从 root 开始
        Returns:
            选出的下一个扩展节点
        """
        selected = node or self.root
        logger.debug(f"Selecting next from node {selected.id}")
        while selected and not selected.is_terminal:
            logger.debug(f"At node {selected.id} stage={selected.stage} visits={selected.visits} expected_child_count={selected.expected_child_count} children={selected.num_children} is_buggy={selected.is_buggy} continue_improve={selected.continue_improve}")
            if not selected.is_fully_expanded(self.search_cfg):
                if selected.is_buggy and selected.is_debug_success:
                    selected = self._uct_select(selected)
                elif selected.continue_improve and selected.children:
                    selected = self._uct_select(selected)
                else:
                    logger.debug(f"Selected for expansion: {selected.id} (not fully expanded)")
                    return selected
            else:
                selected = self._uct_select(selected)
        logger.debug(f"Final selected node: {selected.id if selected else None}")
        return selected

    def ingest_result(
        self,
        node: UCTNode,
        review: MetricReview,
        *,
        debug_budget_exhausted: bool = False,
    ) -> float:
        """写回节点执行结果，计算奖励并回传。

        Args:
            node: 当前节点
            review: 解析后的度量结果
            debug_budget_exhausted: 调试预算是否耗尽（超出则终止）
        Returns:
            本次回传的奖励值
        """
        node.finish_time = time.time()
        node.analysis = review.summary
        node.is_buggy = review.is_bug or review.metric is None or not review.has_submission
        node.is_valid = not node.is_buggy
        node.metric = (
            WorstMetricValue()
            if node.is_buggy
            else MetricValue(review.metric, maximize=review.maximize)
        )
        # Reject nodes whose metric direction conflicts with existing best node.
        if (
            node.is_buggy is False
            and self.best_node
            and self.best_node.metric
            and node.metric.maximize != self.best_node.metric.maximize
        ):
            logger.warning(
                "Metric direction conflict: node %s maximize=%s vs best maximize=%s. Marking node as buggy.",
                node.id,
                node.metric.maximize,
                self.best_node.metric.maximize,
            )
            node.metric = WorstMetricValue()
            node.is_buggy = True
            node.is_valid = False
            node.analysis = f"{node.analysis or ''}\n[metric] direction mismatch with best node".strip()
        node.continue_improve = not node.is_buggy and node.metric.value is not None
        if node.parent and node.parent.is_buggy and node.is_buggy is False:
            node.parent.is_debug_success = True
            # Mark parent as non-buggy once a child fixed the issue to align with ML-Master semantics.
            node.parent.is_buggy = False

        if node.parent and node.parent.stage != "root":
            node.parent.continue_improve = node.continue_improve

        if debug_budget_exhausted and node.stage == "debug":
            node.is_terminal = True

        # 提交文件格式校验（若配置了 grader）
        if (
            self.grader
            and self.exp_id
            and self.submission_dir
            and not node.is_buggy
        ):
            submission_path = self.submission_dir / f"submission_{node.id}.csv"
            if submission_path.exists():
                ok, res = self.grader(self.exp_id, submission_path)
                if ok:
                    if isinstance(res, dict) and not res.get("is_valid", True):
                        node.is_valid = False
                        node.is_buggy = True
                        node.metric = WorstMetricValue()
                        detail = res.get("result") or res.get("details") or "submission 格式非法"
                        logger.info(f"Grader marked node {node.id} as buggy: {detail}")
                        node.analysis = f"{node.analysis or ''}\n[grading] {detail}".strip()
                else:
                    node.is_valid = False
                    node.is_buggy = True
                    node.metric = WorstMetricValue()
                    node.analysis = f"{node.analysis or ''}\n[grading] grading server 调用失败".strip()

        # 额外的 metric 合法性防护，防止异常放大
        if not node.is_buggy and not self._check_metric_valid(node):
            node.metric = WorstMetricValue()
            node.is_buggy = True
            node.analysis = f"{node.analysis or ''}\n[metric] invalid metric detected".strip()

        # 依据改进成效更新状态，控制继续改进/终止
        self._check_improvement(node)

        # 计算 reward 并回传，同时记录详细信息
        reward = self._get_node_reward(node)
        logger.info(f"Ingested result for node {node.id}: stage={node.stage} is_buggy={node.is_buggy} metric={getattr(node.metric, 'value', None)} reward={reward:.3f}")
        self._backpropagate(node, reward)
        logger.debug(f"After backpropagate: node {node.id} visits={node.visits} total_reward={node.total_reward}")

        # Record initial stats the first time this node itself is ingested.
        if node.initial_reward is None:
            node.initial_reward = reward
            node.initial_total_reward = node.total_reward
            node.initial_visits = node.visits
            # Cache initial uct value at first ingestion for logging.
            try:
                parent_visits = node.parent.visits if node.parent else 1
                node.initial_uct = node.uct_value(self._exploration_constant(), parent_visits)
            except Exception:
                node.initial_uct = None

        # Persist snapshots for current node and its ancestors with latest rewards.
        if self.snapshot_fn:
            submission_path = (
                self.submission_dir / f"submission_{node.id}.csv"
                if self.submission_dir and (self.submission_dir / f"submission_{node.id}.csv").exists()
                else None
            )
            current = node
            while current:
                sub = submission_path if current is node else None
                try:
                    self.snapshot_fn(current, sub, review, reward)
                except Exception as exc:
                    logger.warning("Snapshot callback failed for node %s: %s", current.id, exc)
                current = current.parent  # type: ignore[assignment]

        self.current_step += 1
        return reward

    def set_snapshot_fn(
        self,
        fn: Callable[[UCTNode, Optional[Path], MetricReview, float], None],
    ) -> None:
        """Register a callback to persist node snapshots after each backprop."""
        self.snapshot_fn = fn

    # ---- 内部实现 ------------------------------------------------------ #

    def _backpropagate(self, node: UCTNode, reward: float) -> None:
        current = node
        while current is not None:
            if current.stage == "draft" and current.locked:
                current.locked = False
            current.update_reward(reward)
            logger.debug(f"Backpropagate node {current.id}: visits={current.visits} total_reward={current.total_reward}")
            current = current.parent  # type: ignore[assignment]

    def _get_node_reward(self, node: UCTNode) -> float:
        if node.is_buggy or node.metric.value is None:
            return -1.0

        reward = 1.0
        parent = node.parent
        if parent and parent.is_buggy:
            reward += 1.0

        if (
            self.best_node
            and self.best_node.metric
            and self.best_node.metric.maximize == node.metric.maximize
            and self.best_metric is not None
            and node.metric.value is not None
        ):
            improvement = (
                node.metric.value - self.best_metric
                if node.metric.maximize
                else self.best_metric - node.metric.value
            )
            if improvement > 0:
                reward += 1.0

        if node.metric.value is not None:
            # Only update best when metric direction matches current best (or when best is None).
            if self.best_node is None or self.best_node.metric.maximize == node.metric.maximize:
                # Guard again before writing best_metric to avoid invalid spikes.
                if self._check_metric_valid(node):
                    if self.best_metric is None or (self.best_node and node.metric > self.best_node.metric):
                        self.best_metric = node.metric.value
                        self.best_node = node

        return reward

    def _check_metric_valid(self, node: UCTNode, upper_bound: int | None = None) -> bool:
        """Guard against abnormally large/small metrics compared to current best."""
        bound = upper_bound or getattr(self.search_cfg, "invalid_metric_upper_bound", 100)
        v1 = self.best_metric
        v2 = node.metric.value
        if v1 is None or v2 is None:
            return True
        if v1 == 0 or v2 == 0:
            return abs(v1 - v2) <= bound
        ratio = max(abs(v1), abs(v2)) / min(abs(v1), abs(v2))
        return ratio <= bound

    def _check_improvement(self, node: UCTNode) -> None:
        """Update improvement bookkeeping similar to ML-Master MCTSAgent."""
        parent = node.parent
        local_best = node.local_best_node or (parent.local_best_node if parent else None) or parent
        scfg = self.search_cfg

        if node.is_buggy is False:
            new_metric = node.metric.value
            if parent and parent.is_buggy:
                node.continue_improve = False
                node.is_terminal = False
                return

            if new_metric is not None and local_best and local_best.metric.value is not None:
                improvement = (
                    new_metric - local_best.metric.value
                    if node.metric.maximize
                    else local_best.metric.value - new_metric
                )
                if improvement < scfg.metric_improvement_threshold:
                    if local_best.improve_failure_depth < scfg.max_improve_failure:
                        local_best.improve_failure_depth += 1
                        node.continue_improve = True
                    else:
                        node.continue_improve = False
                        node.is_terminal = True
                else:
                    node.local_best_node = node
                    node.continue_improve = True
                    local_best.improve_failure_depth = 0
            elif new_metric is not None:
                node.local_best_node = node
                node.continue_improve = True
            else:
                node.continue_improve = False
        elif node.is_buggy is True:
            # If repeatedly debugging without success, eventually stop.
            if node.debug_depth >= scfg.back_debug_depth:
                if node.debug_depth >= scfg.max_debug_depth:
                    node.is_terminal = True
        else:
            node.continue_improve = False


    def _uct_select(self, node: UCTNode) -> UCTNode:
        c_val = self._exploration_constant()
        if node.stage == "root":
            unlocked = [child for child in node.children if not child.locked]
            if not unlocked:
                return node
            # 记录可选子节点的 UCT 值
            scores = [(child, child.uct_value(c_val, node.visits)) for child in unlocked]
            for ch, sc in scores:
                logger.debug(f"Root child {ch.id} uct={sc:.4f} visits={ch.visits} total_reward={ch.total_reward} locked={ch.locked}")
            picked = max(unlocked, key=lambda child: child.uct_value(c_val, node.visits))
            if picked.stage == "draft":
                picked.locked = True
            return picked
        # 对非 root 节点也记录 UCT 值
        scores = [(child, child.uct_value(c_val, node.visits)) for child in node.children]
        for ch, sc in scores:
            logger.debug(f"Child {ch.id} uct={sc:.4f} stage={ch.stage} visits={ch.visits} total_reward={ch.total_reward}")
        return max(node.children, key=lambda child: child.uct_value(c_val, node.visits))

    def _exploration_constant(self) -> float:
        cfg = self.decay_cfg
        t = self.current_step
        if cfg.decay_type == "linear":
            c_val = _linear_decay(t, cfg.exploration_constant, cfg.linear_alpha, cfg.lower_bound)
        elif cfg.decay_type == "exponential":
            c_val = _exponential_decay(
                t,
                cfg.exploration_constant,
                cfg.exponential_gamma,
                cfg.lower_bound,
            )
        elif cfg.decay_type == "piecewise":
            t1 = round(cfg.piecewise_phase_ratios[0] * max(self.current_step, 1))
            t2 = round(cfg.piecewise_phase_ratios[1] * max(self.current_step, 1))
            c_val = _piecewise_decay(
                t,
                cfg.exploration_constant,
                t1,
                t2,
                cfg.piecewise_alpha,
                cfg.lower_bound,
            )
        elif cfg.decay_type == "dynamic_piecewise":
            c_val = _dynamic_piecewise_decay(
                steps_limit=max(self.current_step, 1),
                n_nodes=self.current_step,
                initial_c=cfg.exploration_constant,
                start_time=self.search_start_time,
                time_limit=self.time_limit or 1e6,
                alpha=cfg.dynamic_alpha,
                lower_bound=cfg.lower_bound,
                phase_ratios=cfg.dynamic_phase_ratios,
            )
        else:
            c_val = cfg.exploration_constant

        logger.debug(f"Exploration constant chosen: {c_val:.4f} (decay_type={cfg.decay_type} step={self.current_step})")
        return c_val
