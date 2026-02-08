---
name: compliance-guardian
description: Validates task safety, software licensing, and research ethics. Use before executing restricted software or providing sensitive technical details. Tool via use_skill run_script check_compliance.py "<plan_description>" "<intended_command>". Returns JSON with allowed, reason, suggestion. Redirects VASP→ABACUS/remote, Gaussian→ORCA/remote; blocks synthesis recipes for energetic materials; blocks dangerous shell commands.
skill_type: operator
---

# Compliance Guardian Skill

A mandatory filter for sensitive operations. It acts as a gatekeeper for:

1. **Commercial / restricted software**: Prevents unauthorized local execution of VASP, Gaussian. Writing input files is allowed; running the binary is not. Suggests ABACUS (for VASP) or remote submission; Gaussian suggests ORCA (when available) or remote.
2. **Research safety / dual-use**: Distinguishes theoretical research (allowed) from practical manufacturing/synthesis of dangerous substances (restricted). Energetic materials: DFT, detonation physics, literature, crystal structure — allowed. Synthesis recipes, formulation ratios, step-by-step manufacturing — denied. Drugs/toxins: interaction simulation allowed; synthesis denied.
3. **System security**: Blocks dangerous shell commands (e.g. rm -rf /, destructive syscalls).

## Tool (via use_skill)

- **run_script** with **script_name**: `check_compliance.py`, **script_args**: two arguments — plan description and intended command (quote if containing spaces).
  - Example: `use_skill` with action=`run_script`, script_name=`check_compliance.py`, script_args=`"optimize structure with VASP locally" "vasp_std"`
  - Output: JSON string with `allowed` (bool), `reason` (str), `suggestion` (str).

## Rules

- **VASP / Gaussian**: Local execution is ALWAYS denied. Allowed: writing INCAR/INPUT files, analyzing outputs. Suggest ABACUS (VASP alternative) or remote submission; for Gaussian suggest ORCA or remote.
- **Energetic materials**: Theoretical calculation (DFT, MD, detonation velocity, stability) and literature review are ALLOWED. Synthesis recipes, manufacturing processes, formulation ratios, or weaponization details are DENIED.
- **Drugs / toxins**: Interaction simulation and property calculation are ALLOWED. Synthesis or procurement details are DENIED.
- **Dangerous commands**: Commands that risk system integrity (e.g. rm -rf /, raw disk, credential abuse) are BLOCKED.
