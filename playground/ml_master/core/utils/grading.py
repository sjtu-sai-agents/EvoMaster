"""评测服务器辅助工具（用于提交格式校验）。"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Iterable, Tuple

try:
    from .grading_server import ensure_grading_server, stop_grading_server
except ImportError:
    def ensure_grading_server(dataset_root: str | Path, server_urls: Iterable[str]) -> str | None:
        """Fallback when local grading_server helper is unavailable."""
        logger = logging.getLogger(__name__)
        logger.warning(
            "grading_server helper not found; skip auto-start. "
            "Please make sure grading_servers are already running."
        )
        return None

    def stop_grading_server(timeout: int = 5) -> bool:
        return False

try:
    import requests
    _HAS_REQUESTS = True
    _REQ_ERR: str | None = None
except ImportError as e:
    _HAS_REQUESTS = False
    _REQ_ERR = str(e)

logger = logging.getLogger(__name__)

def is_server_online(server_urls: Iterable[str], timeout: int = 60, max_retries: int | None = None) -> Tuple[bool, str]:
    """检查评测服务器的健康状况。"""
    if not _HAS_REQUESTS:
        logger.warning("requests not installed; skip grading health check. Missing module: %s", _REQ_ERR)
        return False, ""

    urls = list(server_urls)
    if not urls:
        return False, ""
    retries = max_retries or len(urls)
    idx = random.randrange(len(urls))
    for attempt in range(retries):
        server_url = urls[idx % len(urls)]
        try:
            resp = requests.get(f"{server_url}/health", timeout=timeout)
            if resp.status_code == 200:
                logger.info(f"grading server online: {server_url}")
                return True, server_url
            logger.warning(f"grading health non-200: {resp.status_code}")
        except requests.RequestException as e:
            logger.error(f"grading health check failed ({server_url}): {e}")
        time.sleep(1)
        idx += 1
    return False, ""

def validate_submission(
    exp_id: str,
    submission_path: Path,
    *,
    server_urls: Iterable[str],
    dataset_root: str | Path | None = None,
    timeout: int = 60,
    max_retries: int = 3,
) -> Tuple[bool, dict | str]:
    """向评测服务器提交 submission.csv 进行格式校验。"""
    if not _HAS_REQUESTS:
        msg = f"requests not installed; cannot call grading server ({_REQ_ERR})"
        logger.warning(msg)
        return False, msg

    urls = list(server_urls)
    if dataset_root:
        started = ensure_grading_server(dataset_root, server_urls=urls)
        if started and started not in urls:
            urls.append(started)

    online, server_url = is_server_online(urls, timeout=timeout, max_retries=max_retries)
    if not online:
        return False, "grading server unavailable"
    for attempt in range(max_retries):
        try:
            with open(submission_path, "rb") as f:
                files = {"file": f}
                resp = requests.post(f"{server_url}/validate", files=files, headers={"exp-id": exp_id}, timeout=timeout)
            data = resp.json()
            if "error" in data:
                logger.error(f"grading server error: {data}")
                return False, data.get("details", data["error"])
            return True, data
        except requests.Timeout:
            logger.error(f"grading validate timeout ({server_url}), attempt {attempt+1}/{max_retries}")
        except requests.RequestException as e:
            logger.error(f"grading validate failed ({server_url}): {e}")
        except Exception as e:
            logger.error(f"grading validate unexpected error: {e}")
        time.sleep(1)
    return False, "grading server call failed"


def shutdown_embedded_grading_server(timeout: int = 5) -> bool:
    """Shutdown embedded grading server started by current process."""
    return stop_grading_server(timeout=timeout)
