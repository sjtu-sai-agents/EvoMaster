"""Upload local files to Aliyun OSS for calculation MCP tools.

Uses oss2 when available; env: OSS_ENDPOINT, OSS_BUCKET_NAME, credentials
(via EnvironmentVariableCredentialsProvider).
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_oss2: Optional[object] = None


def _get_oss2():
    global _oss2
    if _oss2 is None:
        try:
            import oss2
            from oss2.credentials import EnvironmentVariableCredentialsProvider
            _oss2 = (oss2, EnvironmentVariableCredentialsProvider)
        except ImportError:
            raise ImportError(
                "Calculation OSS upload requires oss2. Install with: pip install oss2"
            )
    return _oss2


def upload_file_to_oss(
    local_path: Path,
    workspace_root: Path,
    *,
    oss_prefix: str = "evomaster/calculation",
) -> str:
    """Upload a local file to OSS and return its public URL."""
    path = Path(local_path)
    if not path.is_absolute():
        path = (workspace_root / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    oss2_module, cred_provider = _get_oss2()
    endpoint = os.environ.get("OSS_ENDPOINT")
    bucket_name = os.environ.get("OSS_BUCKET_NAME")
    if not endpoint or not bucket_name:
        raise RuntimeError(
            "Calculation OSS upload requires OSS_ENDPOINT and OSS_BUCKET_NAME in environment. "
            "Set them in .env at project root (run.py loads .env when starting). "
            "Also set OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET for upload."
        )

    auth = oss2_module.ProviderAuth(cred_provider())
    bucket = oss2_module.Bucket(auth, endpoint, bucket_name)
    filename = path.name
    oss_key = f"{oss_prefix}/{int(time.time())}_{filename}"
    with open(path, "rb") as f:
        bucket.put_object(oss_key, f.read())
    host = endpoint.replace("https://", "").replace("http://", "").split("/")[0]
    url = f"https://{bucket_name}.{host}/{oss_key}"
    logger.debug("Uploaded %s -> %s", path, url)
    return url
