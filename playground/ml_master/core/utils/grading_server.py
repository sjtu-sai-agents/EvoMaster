"""Embedded grading server utilities for ml_master.

Provides:
- best-effort reuse of healthy existing grading endpoints
- thread-safe lazy startup of an embedded Flask server
- graceful shutdown for the embedded server started by this process
"""

from __future__ import annotations

import atexit
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Iterable, Tuple
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from mlebench.grade import validate_submission as _bench_validate
from mlebench.registry import registry

logger = logging.getLogger(__name__)

_SERVER_LOCK = threading.Lock()
_SERVER_THREAD: threading.Thread | None = None
_SERVER_HTTPD = None
_SERVER_URL: str | None = None
_SERVER_OWNED: bool = False


def _create_app(base_dir: Path) -> Flask:
    """Create Flask app bound to a dataset directory."""
    app = Flask(__name__)
    private_dir = Path(base_dir)
    new_registry = registry.set_data_dir(private_dir)

    def run_validation(submission: Path, competition_id: str) -> Tuple[bool, str]:
        competition = new_registry.get_competition(competition_id)
        is_valid, message = _bench_validate(submission, competition)
        return is_valid, message

    @app.route("/validate", methods=["POST"])
    def validate():
        submission_file = request.files["file"]
        competition_id = request.headers.get("exp-id")
        submission_path = Path("/tmp/submission_to_validate.csv")
        submission_file.save(submission_path)

        try:
            is_valid, result = run_validation(submission_path, competition_id)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": "An unexpected error occurred.", "details": str(exc)}), 500

        return jsonify({"result": result, "is_valid": is_valid})

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "running"}), 200

    return app


def _is_local_url(url: str) -> bool:
    host = urlparse(url).hostname
    return host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _http_get(url: str, timeout: int):
    if _is_local_url(url):
        with requests.Session() as session:
            # Keep global proxies for external requests, but bypass for localhost.
            session.trust_env = False
            return session.get(url, timeout=timeout)
    return requests.get(url, timeout=timeout)


def _parse_host_port(
    url: str,
    default_host: str = "127.0.0.1",
    default_port: int = 5003,
) -> Tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or default_host
    port = parsed.port or default_port
    return host, port


def _is_healthy(url: str, timeout: int = 5) -> bool:
    try:
        resp = _http_get(url.rstrip("/") + "/health", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _wait_for_health(url: str, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_healthy(url, timeout=2):
            return True
        time.sleep(0.5)
    return False


def _is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _is_port_in_use(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check whether TCP port is already occupied."""
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((probe_host, port)) == 0
        except OSError:
            return False


def _pick_bind_target(urls: list[str], default_port: int = 5003) -> Tuple[str, int]:
    """Choose a local host/port to start embedded grading server.

    Strategy:
    - Prefer candidate urls in order.
    - Skip candidates whose local port is occupied.
    - If all candidates are occupied, scan localhost ports from default_port upward.
    """
    candidates: list[Tuple[str, int]] = []
    for url in urls:
        host, port = _parse_host_port(url, default_port=default_port)
        if not _is_local_host(host):
            continue
        candidates.append((host, port))

    if not candidates:
        candidates.append(("127.0.0.1", default_port))

    for host, port in candidates:
        if not _is_port_in_use(host, port):
            return host, port

    scan_host = "127.0.0.1"
    for port in range(default_port, default_port + 200):
        if not _is_port_in_use(scan_host, port):
            return scan_host, port

    return "127.0.0.1", default_port


def ensure_grading_server(
    dataset_root: str | Path | None,
    server_urls: Iterable[str] | None = None,
    startup_timeout: int = 30,
) -> str:
    """Ensure a grading server endpoint is available.

    Reuses healthy endpoints first. Starts embedded server only if needed.
    """
    global _SERVER_THREAD, _SERVER_HTTPD, _SERVER_URL, _SERVER_OWNED  # noqa: PLW0603

    with _SERVER_LOCK:
        urls = list(server_urls or [])
        if not urls:
            urls.append("http://127.0.0.1:5003")

        for url in urls:
            if _is_healthy(url):
                _SERVER_URL = url
                _SERVER_OWNED = False
                return url

        if _SERVER_THREAD and _SERVER_THREAD.is_alive() and _SERVER_URL:
            if _wait_for_health(_SERVER_URL, timeout=startup_timeout):
                return _SERVER_URL

        if dataset_root is None:
            logger.warning("dataset_root not provided; cannot auto-start embedded grading server.")
            return ""

        data_dir = Path(dataset_root).expanduser().resolve()
        if not data_dir.exists():
            logger.error("dataset_root does not exist: %s", data_dir)
            return ""

        bind_host, bind_port = _pick_bind_target(urls, default_port=5003)
        server_url = f"http://{bind_host}:{bind_port}"
        app = _create_app(data_dir)
        httpd = make_server(bind_host, bind_port, app)
        thread = threading.Thread(
            target=httpd.serve_forever,
            name=f"grading-server-{bind_host}:{bind_port}",
            daemon=True,
        )
        thread.start()
        _SERVER_HTTPD = httpd
        _SERVER_THREAD = thread
        _SERVER_URL = server_url
        _SERVER_OWNED = True

        if _wait_for_health(server_url, timeout=startup_timeout):
            logger.info("Embedded grading server started at %s", server_url)
            return server_url

        logger.error("Failed to start embedded grading server at %s within %ss", server_url, startup_timeout)
        # Best-effort rollback to avoid leaving a dangling server object.
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
        _SERVER_HTTPD = None
        _SERVER_THREAD = None
        _SERVER_URL = None
        _SERVER_OWNED = False
        return ""


def stop_grading_server(timeout: int = 5) -> bool:
    """Stop embedded grading server started by current process.

    Returns True when a local embedded process was stopped.
    """
    global _SERVER_THREAD, _SERVER_HTTPD, _SERVER_URL, _SERVER_OWNED  # noqa: PLW0603

    with _SERVER_LOCK:
        if not _SERVER_OWNED or _SERVER_HTTPD is None:
            return False

        thread = _SERVER_THREAD
        httpd = _SERVER_HTTPD
        stopped = False
        try:
            httpd.shutdown()
            httpd.server_close()
            if thread:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning("Embedded grading server did not stop within %ss", timeout)
                else:
                    stopped = True
                    logger.info("Embedded grading server stopped")
            else:
                stopped = True
        except Exception as exc:
            logger.warning("Failed to stop embedded grading server cleanly: %s", exc)

        _SERVER_THREAD = None
        _SERVER_HTTPD = None
        _SERVER_URL = None
        _SERVER_OWNED = False
        return stopped


atexit.register(stop_grading_server)
