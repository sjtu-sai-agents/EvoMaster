"""
EvoMaster-compatible MCP server (Streamable HTTP).

This exposes the code-execution capability via the standard MCP protocol so that
EvoMaster can connect using:
  transport: "http"
  url: "http://127.0.0.1:8000/mcp"

Tools:
  - execute: run python code in a per-session persistent namespace
  - reset_session: clear a session namespace
  - web_search: search the web (via api_proxy /search)
  - web_parse: parse/analyze web or PDF content with LLM (calls BASE-TOOL-Server in-process)
"""

import io
import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import aiohttp
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


PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Config paths: this file is in mcp_sandbox/MCP/, configs are in mcp_sandbox/configs/
_SANDBOX_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _SANDBOX_ROOT / "configs"
_BASE_TOOL_SERVER = _SANDBOX_ROOT / "MCP" / "server" / "BASE-TOOL-Server"

_WEB_PARSE_SETUP_DONE = False


def _ensure_web_parse_env() -> None:
    """Ensure BASE-TOOL-Server is on path and cwd so web_parse imports can find configs."""
    global _WEB_PARSE_SETUP_DONE
    if _WEB_PARSE_SETUP_DONE:
        return
    if _BASE_TOOL_SERVER.exists():
        import sys
        if str(_BASE_TOOL_SERVER) not in sys.path:
            sys.path.insert(0, str(_BASE_TOOL_SERVER))
        if os.getcwd() != str(_SANDBOX_ROOT):
            os.chdir(_SANDBOX_ROOT)
    _WEB_PARSE_SETUP_DONE = True


def _get_content_type(url: str) -> str:
    try:
        import requests
        r = requests.head(url, allow_redirects=True, timeout=3)
        return (r.headers.get("Content-Type") or "").lower()
    except Exception:
        return ""


def _get_api_base_url() -> str:
    """API base URL for search/web_parse (api_proxy)."""
    url = os.getenv("API_BASE_URL")
    if url:
        return url.rstrip("/")
    config_path = _CONFIG_DIR / "mcp_config.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return json.load(f).get("tool_api_url", "http://127.0.0.1:1234").rstrip("/")
    return "http://127.0.0.1:1234"


def _get_serper_api_key() -> str:
    """Serper API key for web_search."""
    key = os.getenv("SERPER_API_KEY")
    if key:
        return key
    config_path = _CONFIG_DIR / "web_agent.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return json.load(f).get("serper_api_key", "")
    return ""


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


@mcp.tool()
async def web_search(
    query: str,
    top_k: int = 10,
    region: str = "us",
    lang: str = "en",
    depth: int = 0,
) -> dict[str, Any]:
    """Search the web via Google (Serper). Returns list of organic results.

    Args:
        query: Search query.
        top_k: Max number of results (default 10).
        region: Search region (e.g. us, uk, cn).
        lang: Language (e.g. en, zh-CN).
        depth: Search depth (0 = default).

    Returns:
        Dict with 'organic' list of {title, link, snippet, ...}, or 'error' on failure.
    """
    base = _get_api_base_url()
    key = _get_serper_api_key()
    payload = {
        "query": query,
        "serper_api_key": key,
        "top_k": top_k,
        "region": region,
        "lang": lang,
        "depth": depth,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{base}/search", json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()
        return {"organic": data} if isinstance(data, list) else data
    except Exception as e:
        return {"error": str(e), "organic": []}


@mcp.tool()
async def web_parse(
    link: str,
    user_prompt: str,
    llm: str = "gpt-4o",
) -> dict[str, Any]:
    """Parse and analyze web or PDF content with an LLM. Use for pages or PDFs/arXiv.

    Args:
        link: URL of the web page or PDF.
        user_prompt: Question or analysis request about the content.
        llm: Model name for parsing (default gpt-4o).

    Returns:
        Dict with 'content', 'urls', 'score'; or 'error' on failure.
    """
    try:
        _ensure_web_parse_env()
        if not _BASE_TOOL_SERVER.exists():
            return {"content": "", "urls": [], "score": -1, "error": "BASE-TOOL-Server not found"}
        is_pdf = (
            ".pdf" in link
            or "arxiv.org/abs" in link
            or "arxiv.org/pdf" in link
            or "pdf" in _get_content_type(link)
        )
        if is_pdf:
            from paper_agent.paper_parse import paper_qa_link
            return await paper_qa_link(link, user_prompt, llm)
        from web_agent.web_parse import parse_htmlpage
        return await parse_htmlpage(link, user_prompt, llm)
    except Exception as e:
        return {"content": "", "urls": [], "score": -1, "error": str(e)}


if __name__ == "__main__":
    # Streamable HTTP MCP server on http://HOST:PORT/mcp
    mcp.run(transport="streamable-http")

