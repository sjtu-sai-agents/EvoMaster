"""
Core logic for reading/decoding FULL file content with automatic compression and encoding detection.
Modified to output EVERYTHING without truncation.
"""
import os
import gzip
import json
import base64
from typing import Dict, Any, Tuple, ClassVar

from pydantic import Field

from evomaster.agent.tools.base import BaseTool, BaseToolParams


def decode_text_file(file_content: bytes) -> str:
    """
    Decode bytes content to text using various encoding detection methods.
    """
    encodings = [
        "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be",
        "utf-32", "utf-32-le", "utf-32-be", "gbk", "gb2312",
        "iso-8859-1", "latin-1", "cp1252", "ascii",
    ]
    for encoding in encodings:
        try:
            return file_content.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return file_content.decode("utf-8", errors="ignore")


def is_gzip_file(file_content: bytes) -> bool:
    """Check if the file content is gzip compressed."""
    return file_content.startswith(b"\x1f\x8b\x08")


def is_zstd_file(file_content: bytes) -> bool:
    """Check if the file content is zstandard compressed."""
    return len(file_content) >= 4 and file_content.startswith(b"\x28\xb5\x2f\xfd")


def is_brotli_file(file_content: bytes) -> bool:
    """Check if the file content is brotli compressed."""
    return len(file_content) >= 2 and file_content.startswith(b"\x1b\x78")


def is_lz4_file(file_content: bytes) -> bool:
    """Check if the file content is lz4 compressed."""
    return len(file_content) >= 4 and file_content.startswith(b"\x04\x22\x4d\x18")


def decode_file_content(file_path: str) -> str:
    """
    Decode file content with automatic detection of compression and encoding.
    """
    try:
        with open(file_path, "rb") as f:
            content = f.read()

        if is_zstd_file(content):
            return "[File is Zstandard (.zst) compressed. To decompress install: pip install zstandard]"

        if is_brotli_file(content):
            return "[File is Brotli (.br) compressed. To decompress install: pip install brotli]"

        if is_lz4_file(content):
            return "[File is LZ4 compressed. To decompress install: pip install lz4]"

        if is_gzip_file(content):
            try:
                content = gzip.decompress(content)
            except Exception as e:
                return f"[Error decompressing gzip file: {e}]"

        return decode_text_file(content)
    except Exception as e:
        return f"[Error decoding file: {str(e)}]"


def analyze_binary_json_file(file_content: str) -> Tuple[str, Dict[str, Any]]:
    """
    Analyze a binary JSON file and return the FULL content formatted.
    """
    decode_attempts = []

    def format_json(data):
        return json.dumps(data, indent=2, ensure_ascii=False)

    try:
        parsed_data = json.loads(file_content)
        decode_attempts.append(("Direct JSON parsing", "Success"))
        return format_json(parsed_data), {"direct_parsing": parsed_data}
    except json.JSONDecodeError:
        decode_attempts.append(("Direct JSON parsing", "Failed"))
    except Exception:
        decode_attempts.append(("Direct JSON parsing", "Failed with exception"))

    try:
        decoded_content = base64.b64decode(file_content)
        parsed_data = json.loads(decoded_content.decode("utf-8"))
        decode_attempts.append(("Base64 decoding", "Success"))
        return format_json(parsed_data), {"base64_decoding": parsed_data}
    except Exception:
        decode_attempts.append(("Base64 decoding", "Failed"))

    try:
        decoded_content = file_content.encode("utf-8").decode("utf-16")
        parsed_data = json.loads(decoded_content)
        decode_attempts.append(("UTF-16 decoding", "Success"))
        return format_json(parsed_data), {"utf16_decoding": parsed_data}
    except Exception:
        decode_attempts.append(("UTF-16 decoding", "Failed"))

    try:
        decompressed_content = gzip.decompress(
            file_content.encode("latin-1") if isinstance(file_content, str) else file_content
        )
        parsed_data = json.loads(decompressed_content.decode("utf-8"))
        decode_attempts.append(("Gzip decompression", "Success"))
        return format_json(parsed_data), {"gzip_decompression": parsed_data}
    except Exception:
        decode_attempts.append(("Gzip decompression", "Failed"))

    try:
        content_bytes = file_content.encode("utf-8") if isinstance(file_content, str) else file_content
        hex_dump = content_bytes[:500].hex()
        analysis_info = f"Unable to decode file as JSON. First 500 bytes as hex: {hex_dump}"
    except Exception as e:
        analysis_info = f"Unable to decode file or generate hex dump: {str(e)}"

    return analysis_info, {"decode_attempts": decode_attempts}


def is_binary_content(file_content: str, sample_size: int = 1000) -> bool:
    """Check if the content is binary data."""
    binary_indicators = [
        "\x00", "\x01", "\x02", "\x03", "\x04", "\x05", "\x06", "\x07", "\x08",
        "\x0b", "\x0c", "\x0e", "\x0f", "\x10", "\x11", "\x12", "\x13", "\x14",
        "\x15", "\x16", "\x17", "\x18", "\x19", "\x1a", "\x1b", "\x1c", "\x1d", "\x1e", "\x1f",
    ]
    return any(indicator in file_content[:sample_size] for indicator in binary_indicators)


def read_and_decode_file(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Read and decode a file, returning both the content and metadata about the file.
    """
    metadata: Dict[str, Any] = {
        "file_size": 0,
        "compression_type": None,
        "encoding": None,
    }
    try:
        metadata["file_size"] = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            content = f.read()

        if content[:4] == b"\x28\xb5\x2f\xfd":
            metadata["compression_type"] = "zstandard"
            return "[File is Zstandard (.zst) compressed. To decompress install: pip install zstandard]", metadata
        if len(content) >= 2 and content.startswith(b"\x1b\x78"):
            metadata["compression_type"] = "brotli"
            return "[File is Brotli (.br) compressed. To decompress install: pip install brotli]", metadata
        if len(content) >= 4 and content.startswith(b"\x04\x22\x4d\x18"):
            metadata["compression_type"] = "lz4"
            return "[File is LZ4 compressed. To decompress install: pip install lz4]", metadata
        if content.startswith(b"\x1f\x8b\x08"):
            metadata["compression_type"] = "gzip"
            try:
                content = gzip.decompress(content)
            except Exception:
                pass

        encodings = ["utf-8", "utf-16", "utf-32", "gbk", "gb2312", "latin-1"]
        decoded_content = None
        for encoding in encodings:
            try:
                decoded_content = content.decode(encoding)
                metadata["encoding"] = encoding
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if decoded_content is None:
            decoded_content = content.decode("utf-8", errors="ignore")
            metadata["encoding"] = "utf-8-with-errors"
        return decoded_content, metadata
    except Exception as e:
        return f"[Error reading file: {str(e)}]", metadata


def peek_file(
    file_path: str,
    *,
    max_preview_lines: int = -1,
    include_preview: bool = True,
) -> Dict[str, Any]:
    """
    Read and return the FULL content of a file, handling compression and encoding.

    Args:
        file_path: Path to the file.
        max_preview_lines: Ignored (legacy parameter).
        include_preview: If True, adds 'preview' or 'binary_analysis' field with full content.

    Returns:
        Dict with:
          - content: Decoded full text content.
          - metadata: file_size, compression_type, encoding.
          - is_binary: True if content looks binary.
          - preview: Full content (same as 'content', provided for convenience).
          - binary_analysis: If binary/JSON, this contains the FULL pretty-printed JSON structure.
    """
    content, metadata = read_and_decode_file(file_path)
    result: Dict[str, Any] = {
        "content": content,
        "metadata": metadata,
        "is_binary": is_binary_content(content),
    }

    if include_preview:
        if result["is_binary"]:
            analysis_info, _ = analyze_binary_json_file(content)
            result["binary_analysis"] = analysis_info
        else:
            result["preview"] = content

    return result


# --- EvoMaster BaseTool wrapper ---


class PeekFileToolParams(BaseToolParams):
    """Read full file content with automatic compression and encoding detection."""

    name: ClassVar[str] = "peek_file"

    file_path: str = Field(
        description="Absolute or relative path to the file to read (e.g. /workspace/INCAR or _tmp/InputScriptOrchestrator/data/vasp_parameters.json).",
    )
    include_preview: bool = Field(
        default=True,
        description="If true, include full content in preview or binary_analysis field.",
    )


class PeekFileTool(BaseTool):
    """Built-in tool: read full file content with encoding/compression detection."""

    name: ClassVar[str] = "peek_file"
    params_class: ClassVar[type[BaseToolParams]] = PeekFileToolParams

    def execute(self, session: Any, args_json: str) -> tuple[str, dict]:
        try:
            params = self.parse_params(args_json)
            assert isinstance(params, PeekFileToolParams)
            result = peek_file(
                params.file_path,
                include_preview=params.include_preview,
            )
            # Return a concise observation for the agent; full content in result
            content = result.get("content", "")
            preview = result.get("preview") or result.get("binary_analysis") or content
            meta = result.get("metadata", {})
            obs_lines = [
                f"file_path: {params.file_path}",
                f"metadata: {meta}",
                f"is_binary: {result.get('is_binary', False)}",
            ]
            if result.get("binary_analysis"):
                obs_lines.append("binary_analysis (full):")
                obs_lines.append(result["binary_analysis"])
            else:
                obs_lines.append("preview (full content):")
                obs_lines.append(preview)
            return "\n".join(obs_lines), {"result": result}
        except Exception as e:
            self.logger.warning("peek_file failed: %s", e)
            return f"Error: {e}", {"error": str(e)}


def get_peek_file_tool() -> PeekFileTool:
    """Return a single PeekFileTool instance for registration."""
    return PeekFileTool()
