from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, send_from_directory, request

from .build_tree import build_tree_payload

logger = logging.getLogger("ml_master_vis")


def create_app(run_dir: Path) -> Flask:
    app = Flask(
        __name__,
        static_folder="static",
        static_url_path="/static",
    )

    # Cache (simple, in-memory). For large trees you can add TTL.
    cache: Dict[str, Any] = {"payload": None, "run_dir": str(run_dir)}

    def get_payload(force: bool = False) -> Dict[str, Any]:
        if force or cache["payload"] is None:
            payload = build_tree_payload(run_dir)
            cache["payload"] = payload
        return cache["payload"]

    @app.get("/")
    def index():
        # Serve static index.html
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "run_dir": str(run_dir)})

    @app.get("/api/tree")
    def api_tree():
        force = request.args.get("refresh", "0") in ("1", "true", "yes")
        payload = get_payload(force=force)
        # Strip internal map from response
        resp = {k: v for k, v in payload.items() if k != "_nodes_by_id"}
        return jsonify(resp)

    @app.get("/api/node/<node_id>")
    def api_node(node_id: str):
        payload = get_payload(force=False)
        nodes_by_id = payload.get("_nodes_by_id", {}) or {}
        if node_id == "__root__":
            return jsonify({"id": "__root__", "stage": "root", "note": "virtual root"})
        node = nodes_by_id.get(node_id)
        if not node:
            return jsonify({"error": "node not found", "id": node_id}), 404
        return jsonify(node)

    @app.get("/api/nodes")
    def api_nodes_list():
        """
        Optional: list nodes for search/autocomplete.
        Returns [{id, stage, metric, uct_value, visits, parent}]
        """
        payload = get_payload(force=False)
        nodes_by_id = payload.get("_nodes_by_id", {}) or {}
        out = []
        for nid, n in nodes_by_id.items():
            out.append({
                "id": nid,
                "stage": n.get("stage"),
                "metric": n.get("metric"),
                "uct_value": n.get("uct_value"),
                "visits": n.get("visits"),
                "parent": n.get("parent"),
            })
        return jsonify(out)

    return app


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser("ml_master_vis")
    p.add_argument("--run_dir", required=True, help="EvoMaster run dir, e.g. runs/ml_master_20260204_115212")
    p.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    p.add_argument("--port", default=8765, type=int, help="bind port (default 8765)")
    p.add_argument("--debug", action="store_true", help="flask debug mode")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise SystemExit(f"run_dir not found: {run_dir}")

    app = create_app(run_dir)
    logger.info("ml_master_vis serving run_dir=%s", run_dir)
    logger.info("open: http://%s:%s/", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
