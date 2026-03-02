from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BuildStats:
    total_files: int
    parsed_nodes: int
    skipped_files: int
    missing_parents: int
    roots: int
    max_depth: int


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


def load_nodes(nodes_dir: Path) -> Tuple[Dict[str, Dict[str, Any]], BuildStats]:
    """
    Load all *.json under nodes_dir, return:
      - nodes_by_id: id -> raw json dict
      - stats
    """
    if not nodes_dir.exists() or not nodes_dir.is_dir():
        empty = BuildStats(
            total_files=0, parsed_nodes=0, skipped_files=0,
            missing_parents=0, roots=0, max_depth=0
        )
        return {}, empty

    files = sorted(nodes_dir.glob("*.json"))
    nodes_by_id: Dict[str, Dict[str, Any]] = {}

    skipped = 0
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                obj = json.load(f)
            node_id = obj.get("id")
            if not node_id or not isinstance(node_id, str):
                skipped += 1
                continue
            # Normalize a few fields (optional but helps front-end)
            obj["metric"] = _safe_float(obj.get("metric"))
            obj["uct_value"] = _safe_float(obj.get("uct_value"))
            obj["reward"] = _safe_float(obj.get("reward"))
            obj["total_reward"] = _safe_float(obj.get("total_reward"))
            obj["visits"] = _safe_int(obj.get("visits"))
            obj["_file"] = str(fp)
            obj["_mtime"] = os.path.getmtime(fp)
            nodes_by_id[node_id] = obj
        except Exception:
            skipped += 1

    # Stats placeholder; fill remaining after linking
    stats = BuildStats(
        total_files=len(files),
        parsed_nodes=len(nodes_by_id),
        skipped_files=skipped,
        missing_parents=0,
        roots=0,
        max_depth=0,
    )
    return nodes_by_id, stats


def build_forest(nodes_by_id: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], BuildStats]:
    """
    Build a forest (list of roots) from nodes_by_id with 'parent' field.
    Return:
      - roots: each is a nested dict suitable for D3 (children)
      - stats
    """
    # Create lightweight node shell with children list
    shells: Dict[str, Dict[str, Any]] = {}
    for nid, raw in nodes_by_id.items():
        shells[nid] = {
            "id": nid,
            "name": nid[:8],
            "parent": raw.get("parent"),
            "stage": raw.get("stage"),
            "metric": raw.get("metric"),
            "maximize": raw.get("maximize"),
            "is_buggy": raw.get("is_buggy"),
            "has_submission": raw.get("has_submission"),
            "reward": raw.get("reward"),
            "visits": raw.get("visits"),
            "total_reward": raw.get("total_reward"),
            "uct_value": raw.get("uct_value"),
            "_mtime": raw.get("_mtime"),
            "children": [],
        }

    missing_parents = 0
    roots: List[Dict[str, Any]] = []

    # Link children to parents
    for nid, node in shells.items():
        pid = node.get("parent")
        if not pid or not isinstance(pid, str) or pid not in shells:
            # No parent or parent not present -> root
            if pid and isinstance(pid, str) and pid not in shells:
                missing_parents += 1
            roots.append(node)
        else:
            shells[pid]["children"].append(node)

    # Depth computation for stats (DFS)
    def depth(n: Dict[str, Any], d: int) -> int:
        if not n["children"]:
            return d
        return max(depth(c, d + 1) for c in n["children"])

    max_depth = 0
    for r in roots:
        max_depth = max(max_depth, depth(r, 0))

    stats = BuildStats(
        total_files=0,
        parsed_nodes=len(nodes_by_id),
        skipped_files=0,
        missing_parents=missing_parents,
        roots=len(roots),
        max_depth=max_depth,
    )
    return roots, stats


def build_tree_payload(run_dir: Path) -> Dict[str, Any]:
    """
    Produce payload for /api/tree:
      {
        "run_dir": "...",
        "nodes_dir": ".../logs/uct_nodes",
        "stats": {...},
        "tree": {...}  # always a single root (virtual root if needed)
      }
    """
    nodes_dir = run_dir / "logs" / "uct_nodes"
    nodes_by_id, load_stats = load_nodes(nodes_dir)
    roots, forest_stats = build_forest(nodes_by_id)

    # Create a single root for D3 even if forest
    if len(roots) == 1:
        tree = roots[0]
    else:
        tree = {
            "id": "__root__",
            "name": "ROOT",
            "parent": None,
            "stage": "root",
            "metric": None,
            "maximize": True,
            "is_buggy": False,
            "has_submission": False,
            "reward": None,
            "visits": None,
            "total_reward": None,
            "uct_value": None,
            "_mtime": None,
            "children": roots,
        }

    payload = {
        "run_dir": str(run_dir),
        "nodes_dir": str(nodes_dir),
        "stats": {
            "total_files": load_stats.total_files,
            "parsed_nodes": load_stats.parsed_nodes,
            "skipped_files": load_stats.skipped_files,
            "missing_parents": forest_stats.missing_parents,
            "roots": forest_stats.roots,
            "max_depth": forest_stats.max_depth,
        },
        "tree": tree,
        # For server-side node detail lookup
        "_nodes_by_id": nodes_by_id,  # internal (strip before sending)
    }
    return payload
