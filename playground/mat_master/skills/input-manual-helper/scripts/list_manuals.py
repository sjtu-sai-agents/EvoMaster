"""
List available input-manual JSON files (bundled in this skill's data/) for writing/validating software inputs.

Usage:
  python list_manuals.py [base_path]

  base_path: optional; directory containing *_parameters.json and pyscf_manual.json.
             Default: data/ next to this script (playground/mat_master/skills/input-manual-helper/data/).

Output: One line per file: software_name|absolute_path
        so the agent can call peek_file(absolute_path) to view the manual structure.
"""

import json
import sys
from pathlib import Path


# Known filenames -> short software label for display
MANUAL_LABELS = {
    "abacus_parameters.json": "ABACUS",
    "abinit_parameters.json": "ABINIT",
    "ase_parameters.json": "ASE",
    "cp2k_parameters.json": "CP2K",
    "deepmd_parameters.json": "DeePMD-kit",
    "dpgen_parameters.json": "DP-GEN",
    "dpgen2_parameters.json": "DPGEN2",
    "gaussian_parameters.json": "Gaussian",
    "lammps_commands_sample.json": "LAMMPS",
    "orca_parameters.json": "ORCA",
    "plumed_parameters.json": "PLUMED",
    "psi4_parameters.json": "PSI4",
    "pyatb_parameters.json": "PyATB",
    "pymatgen_parameters.json": "Pymatgen",
    "pyscf_manual.json": "PySCF",
    "quantum_espresso_parameters.json": "Quantum Espresso",
    "vasp_parameters.json": "VASP",
}


def _infer_software_from_content(file_path: Path) -> str:
    """Try to read first entry's 'software' field from JSON array."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and "software" in first:
                return first["software"]
    except Exception:
        pass
    return file_path.stem


def main() -> None:
    if len(sys.argv) >= 2:
        base = Path(sys.argv[1])
    else:
        # Default: data/ bundled with this skill (input-manual-helper/data/)
        base = Path(__file__).resolve().parent.parent / "data"
    if not base.is_absolute():
        base = base.resolve()

    if not base.exists() or not base.is_dir():
        print(f"Directory not found: {base}", file=sys.stderr)
        print("Usage: python list_manuals.py [base_path]", file=sys.stderr)
        sys.exit(1)

    results = []
    for path in sorted(base.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        name = path.name
        label = MANUAL_LABELS.get(name)
        if label is None:
            label = _infer_software_from_content(path)
        results.append((label, str(path.resolve())))

    for label, abs_path in results:
        print(f"{label}|{abs_path}")


if __name__ == "__main__":
    main()
