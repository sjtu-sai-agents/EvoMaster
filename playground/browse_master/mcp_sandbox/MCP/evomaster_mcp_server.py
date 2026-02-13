"""
EvoMaster-compatible MCP server (Streamable HTTP).

This exposes the code-execution capability via the standard MCP protocol so that
EvoMaster can connect using:
  transport: "http"
  url: "http://127.0.0.1:8001/mcp"

It intentionally keeps the API surface small:
  - execute: run python code in a per-session persistent namespace
  - reset_session: clear a session namespace
"""

import io
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from mcp.server.fastmcp import FastMCP


def _restricted_open(*args, **kwargs):
    mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
    if any(m in str(mode).lower() for m in ("w", "a", "+")):
        raise IOError("File write operations are disabled in mcp-sandbox")
    return open(*args, **kwargs)  # noqa: PTH123 (intentional)


_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.Lock()

# NOTE: keep threads bounded; sandbox code can still spawn threads itself.
_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("MCP_SANDBOX_WORKERS", "16")))


def _get_session_globals(session_id: str) -> dict[str, Any]:
    """Return a per-session globals dict (persistent across calls)."""
    with _SESSIONS_LOCK:
        g = _SESSIONS.get(session_id)
        if g is None:
            g = {
                "__name__": "__mcp_sandbox__",
                "__builtins__": __builtins__,
                # override some dangerous / unwanted builtins
                "open": _restricted_open,
            }
            _SESSIONS[session_id] = g
        return g


PORT = int(os.getenv("PORT", "8001"))
HOST = os.getenv("HOST", "0.0.0.0")

mcp = FastMCP(
    "mcp-sandbox",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
)


@mcp.tool()
async def execute(code: str, timeout: int = 180, session_id: str = "default") -> dict[str, Any]:
    """Execute python code in a (persistent) sandbox session.

    Args:
        code: Python code to execute.
        timeout: Max execution time (seconds).
        session_id: Session identifier. Same id preserves variables/functions across calls.

    Returns:
        Dict with keys: output, error, execution_time, session_id
    """
    code = code or ""
    if not code.strip():
        return {
            "output": "",
            "error": "Code cannot be empty",
            "execution_time": 0.0,
            "session_id": session_id,
        }

    g = _get_session_globals(session_id)
    stdout = io.StringIO()
    stderr = io.StringIO()
    start = time.time()

    def _run():
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(code, g)  # noqa: S102 (intended sandbox behavior)

    try:
        fut = _EXECUTOR.submit(_run)
        fut.result(timeout=timeout)
        err = stderr.getvalue().strip() or None
    except FutureTimeoutError:
        err = f"Execution timed out after {timeout} seconds"
    except SystemExit as se:
        err = f"Code called sys.exit({getattr(se, 'code', None)})"
    except Exception as e:
        err = "".join(traceback.format_exception(type(e), e, e.__traceback__)).strip()

    elapsed = time.time() - start
    out = stdout.getvalue()

    return {
        "output": out,
        "error": err,
        "execution_time": elapsed,
        "session_id": session_id,
    }


@mcp.tool()
async def reset_session(session_id: str = "default") -> dict[str, Any]:
    """Reset (clear) a sandbox session."""
    with _SESSIONS_LOCK:
        existed = session_id in _SESSIONS
        _SESSIONS.pop(session_id, None)
    return {"status": "ok", "session_id": session_id, "existed": existed}


if __name__ == "__main__":
    # Streamable HTTP MCP server on http://HOST:PORT/mcp
    mcp.run(transport="streamable-http")