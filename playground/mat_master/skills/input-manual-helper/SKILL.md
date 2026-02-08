---
name: input-manual-helper
description: "Task = write/demo input file for LAMMPS MSST VASP ABACUS Gaussian CP2K QE etc? MUST use_skill this first: run_script list_manuals.py → peek_file the path → then write. Do not skip to web search."
skill_type: operator
---

# Input Manual Helper Skill

Use when you need to **write** or **validate** input files for computational software (VASP, Gaussian, CP2K, LAMMPS, ABACUS, etc.). The manuals are JSON files under `_tmp/InputScriptOrchestrator/data/` with parameter names, types, syntax templates, and descriptions.

## Workflow

1. **List manuals**: Run `list_manuals.py` (optionally with a base path) to get available manual files and their software names.
2. **Inspect structure**: Call the built-in tool **peek_file** with the path to the relevant `*_parameters.json` or `pyscf_manual.json` to get the **full** manual content. The JSON structure typically includes:
   - `name`, `software`, `paradigm` (e.g. KEY_VALUE), `syntax_template`, `arguments`, `parent_section`, `description`
3. **Write or validate**: Use the manual content to generate correct input files (e.g. INCAR for VASP, INPUT for ABACUS) or to check existing input files against allowed keys and syntax.

## Scripts

- **list_manuals.py** — Lists available manual JSON files under a given data directory. Output: one line per file with `software|path` so you can choose which file to pass to `peek_file`.
  - Usage: `python list_manuals.py [base_path]`
  - Default base_path: `_tmp/InputScriptOrchestrator/data` (relative to workspace root).

## When to use

- Before writing INCAR, KPOINTS, INPUT, or other software-specific input files: use **peek_file** on the corresponding `*_parameters.json` to see valid tags and syntax.
- For post-validation: use **peek_file** to load the manual, then compare the user’s input file keys/sections against the manual (e.g. KEY_VALUE paradigm: key must be in manual; value type from `arguments[].dtype`).

## Important

- **Do not** read the full manual by pasting it into the prompt. Use **peek_file** to fetch the file and then work with the returned content (e.g. search for a specific tag or section).
- Run `list_manuals.py` first to get `software|absolute_path`; then call **peek_file** with that path (paths point to this skill’s `data/` directory).
