"""Path adaptor: Bohrium HTTPS storage and executor/sync logic for calculation MCP tools.

Align with _tmp/MatMaster. Storage 与 executor 鉴权统一通过 evomaster.env.bohrium 读取。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from evomaster.env.bohrium import get_bohrium_storage_config, inject_bohrium_executor

from .oss_upload import upload_file_to_oss

logger = logging.getLogger(__name__)


# Remote tool name -> list of argument names that are input file paths (upload to OSS, pass URL).
CALCULATION_PATH_ARGS: Dict[str, List[str]] = {
    "get_structure_info": ["structure_path"],
    "get_molecule_info": ["molecule_path"],
    "build_bulk_structure_by_template": [],
    "build_bulk_structure_by_wyckoff": [],
    "make_supercell_structure": ["structure_path"],
    "apply_structure_transformation": ["structure_path"],
    "build_molecule_structures_from_smiles": [],
    "add_cell_for_molecules": ["molecule_path"],
    "build_surface_slab": ["material_path"],
    "build_surface_adsorbate": ["surface_path", "adsorbate_path"],
    "build_surface_interface": ["material1_path", "material2_path"],
    "make_defect_structure": ["structure_path"],
    "make_doped_structure": ["structure_path"],
    "make_amorphous_structure": ["molecule_paths"],
    "add_hydrogens": ["structure_path"],
    "generate_ordered_replicas": ["structure_path"],
    "remove_solvents": ["structure_path"],
    "optimize_structure": ["input_structure"],
    "calculate_phonon": ["input_structure"],
    "run_molecular_dynamics": ["initial_structure"],
    "calculate_elastic_constants": ["input_structure"],
    "run_neb": ["initial_structure", "final_structure"],
    "extract_material_data_from_pdf": ["pdf_path"],
    "extract_info_from_webpage": [],
}


def _path_keys_from_schema(input_schema: Optional[Dict[str, Any]]) -> List[str]:
    """From MCP tool input_schema (JSON Schema), return param names that look path/file-related."""
    if not input_schema or not isinstance(input_schema, dict):
        return []
    props = input_schema.get("properties") or {}
    path_keywords = ("path", "file", "url", "structure", "pdf", "cif", "input_structure", "material_path", "surface_path", "adsorbate_path", "molecule_path")
    out = []
    for key, spec in props.items():
        if not isinstance(spec, dict):
            continue
        key_lower = key.lower()
        desc = (spec.get("description") or spec.get("title") or "").lower()
        if any(kw in key_lower for kw in ("path", "structure", "file", "pdf")):
            out.append(key)
        elif any(kw in desc for kw in ("path", "file", "url", "structure", "cif", "input")):
            out.append(key)
    return out


# Schema keys that are NOT input file paths (do not upload / replace with OSS URL).
_NON_PATH_SCHEMA_KEYS = frozenset({"crystal_structure", "output_file"})


def _path_arg_names_from_schema(schema: Optional[Dict[str, Any]]) -> Set[str]:
    """From MCP tool input_schema, collect property names that are input file paths (upload to OSS, pass URL)."""
    out: Set[str] = set()
    if not schema or not isinstance(schema, dict):
        return out
    props = schema.get("properties") or {}
    key_hints = ("structure_path", "molecule_path", "material_path", "surface_path", "adsorbate_path", "input_structure", "initial_structure", "final_structure", "pdf_path")
    for key, prop in props.items():
        key_lower = key.lower()
        if key_lower in _NON_PATH_SCHEMA_KEYS:
            continue
        if any(h in key_lower for h in key_hints):
            out.add(key)
            continue
        if key_lower.endswith("_path") or key_lower == "pdf_path":
            out.add(key)
        elif isinstance(prop, dict):
            desc = (prop.get("description") or prop.get("title") or "").lower()
            if "input" in desc and ("path" in desc or "file" in desc or "url" in desc):
                out.add(key)
    return out


def _is_local_path(value: Any) -> bool:
    if not value or not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https"):
        return False
    if value.lower().startswith("local://"):
        return False
    return True


def _workspace_path_to_local(value: str, workspace_root: Path) -> Path:
    """Map /workspace/... or relative path to actual local Path under workspace_root."""
    value = value.strip().replace("\\", "/")
    if value.startswith("/workspace/"):
        rel = value[len("/workspace/"):].lstrip("/")
        return (workspace_root / rel).resolve()
    if value.startswith("/workspace"):
        rel = value[len("/workspace"):].lstrip("/")
        return (workspace_root / (rel or ".")).resolve()
    path = Path(value)
    if not path.is_absolute():
        return (workspace_root / path).resolve()
    return path


def _resolve_one(value: str, workspace_root: Path) -> str:
    """If value is a local path, upload to OSS and return the OSS URL. Path args must be OSS links for remote MCP."""
    if not _is_local_path(value):
        return value
    path = _workspace_path_to_local(value, workspace_root)
    if not path.exists():
        raise FileNotFoundError(
            f"Path argument file not found: {path}. For calculation MCP tools, input files must exist in workspace so they can be uploaded to OSS and passed as URL."
        )
    if not path.is_file():
        raise ValueError(f"Path argument is not a file: {path}. Only files can be uploaded to OSS.")
    try:
        return upload_file_to_oss(path, workspace_root)
    except Exception as e:
        raise RuntimeError(
            f"Cannot pass local file to calculation MCP: OSS upload required but failed for {path}. "
            "Set OSS_ENDPOINT, OSS_BUCKET_NAME, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET in .env at project root (run.py loads it)."
        ) from e


class CalculationPathAdaptor:
    """Bohrium storage + per-server executor/sync_tools. Sync tools → executor None; else Bohrium executor with env auth."""

    def __init__(self, calculation_executors: Optional[Dict[str, Any]] = None):
        """Optional config: { server_name: { executor: {...}|null, sync_tools: [str] } }. From mcp.calculation_executors."""
        self.calculation_executors = calculation_executors or {}

    def _resolve_executor(self, server_name: str, remote_tool_name: str) -> Optional[Dict[str, Any]]:
        """Return executor for this (server, tool): None if sync tool or no config; else injected Bohrium executor."""
        server_cfg = self.calculation_executors.get(server_name)
        if not server_cfg:
            return None
        sync_tools = server_cfg.get("sync_tools") or []
        if remote_tool_name in sync_tools:
            return None
        executor_template = server_cfg.get("executor")
        if not executor_template or not isinstance(executor_template, dict):
            return None
        return inject_bohrium_executor(executor_template)

    def resolve_args(
        self,
        workspace_path: str,
        args: Dict[str, Any],
        tool_name: str,
        server_name: str,
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Inject executor (None for sync_tools else Bohrium with env), storage=https+Bohrium; path args → OSS URL."""
        out = dict(args)
        remote_name = tool_name
        if server_name and tool_name.startswith(server_name + "_"):
            remote_name = tool_name[len(server_name) + 1 :]
        out["executor"] = self._resolve_executor(server_name, remote_name)
        out["storage"] = get_bohrium_storage_config()

        path_arg_names = set(CALCULATION_PATH_ARGS.get(remote_name, [])) | _path_arg_names_from_schema(input_schema)
        if not path_arg_names or not workspace_path:
            return out

        workspace_root = Path(workspace_path).resolve()
        for key in sorted(path_arg_names):
            if key not in out:
                continue
            val = out[key]
            if isinstance(val, list):
                out[key] = [_resolve_one(str(v), workspace_root) for v in val]
            else:
                out[key] = _resolve_one(str(val), workspace_root)
        return out


def get_calculation_path_adaptor(mcp_config: Optional[Dict[str, Any]] = None) -> CalculationPathAdaptor:
    """Return a calculation path adaptor. If mcp_config has calculation_executors, use it for executor/sync_tools."""
    executors = (mcp_config or {}).get("calculation_executors") if mcp_config is not None else None
    return CalculationPathAdaptor(calculation_executors=executors)
