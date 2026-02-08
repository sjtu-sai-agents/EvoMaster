"""
Compliance Check Script: Validates requests against safety, license, and security rules.

Usage:
  python check_compliance.py "<plan_description>" "<intended_command>"
  Or single JSON arg: python check_compliance.py '{"plan": "...", "command": "..."}'

Output: JSON to stdout with keys allowed (bool), reason (str), suggestion (str).
When allowed is False, an audit line is written to stderr with prefix [COMPLIANCE_DENIED]
so run logs / task_0.log can grep for compliance triggers.
"""

import json
import re
import sys

# Audit log: stderr only (stdout is JSON for the agent). Session captures both, so task logs will show this.
_AUDIT_STDERR = sys.stderr


def _audit_denied(reason: str, suggestion: str, plan: str, command: str) -> None:
    plan_safe = (plan[:200] + "…") if len(plan) > 200 else plan
    cmd_safe = (command[:100] + "…") if len(command) > 100 else command
    line = f"[COMPLIANCE_DENIED] reason={reason!r} plan={plan_safe!r} command={cmd_safe!r} suggestion={suggestion[:80]!r}\n"
    _AUDIT_STDERR.write(line)
    _AUDIT_STDERR.flush()


def _audit_check(allowed: bool, plan: str, command: str) -> None:
    status = "ALLOWED" if allowed else "DENIED"
    plan_safe = (plan[:120] + "…") if len(plan) > 120 else plan
    line = f"[COMPLIANCE_CHECK] result={status} plan={plan_safe!r}\n"
    _AUDIT_STDERR.write(line)
    _AUDIT_STDERR.flush()

# === Hard rules: restricted software (local execution denied; input writing allowed) ===
RESTRICTED_SOFTWARE = {
    "vasp": {
        "pattern": r"(^|\s|/)(vasp_std|vasp_gam|vasp_ncl)(\s|$)",
        "suggestion": "Local VASP execution is restricted. Use ABACUS (mat_abacus) as open-source alternative, or submit VASP jobs to remote clusters via MCP. You may write INCAR/KPOINTS/POSCAR and analyze outputs.",
    },
    "gaussian": {
        "pattern": r"(^|\s|/)(g09|g16|gview|gaussian)(\s|$)",
        "suggestion": "Local Gaussian execution is restricted. Consider ORCA (when available) or submit to remote clusters. You may write input files and analyze outputs.",
    },
}

# Dangerous shell / system commands (blocked)
DANGEROUS_COMMAND_PATTERNS = [
    r"rm\s+-rf\s+/",
    r":\s*\(\s*\)\s*\{\s*[^}]*\|\s*:.*\}",
    r"mkfs\.?\s",
    r"dd\s+if=.*of=/dev",
    r"\bchmod\s+[0-7]{3,4}\s+/",
    r">\s*/dev/sd",
    r"ssh\s+.*\s+root@",
]


def _normalize_for_match(text: str) -> str:
    return (text or "").lower().strip()


def check_hard_rules(plan: str, command: str) -> tuple[bool, str, str]:
    """Check software licensing and dangerous commands. Returns (allowed, reason, suggestion)."""
    plan_lower = _normalize_for_match(plan)
    cmd_lower = _normalize_for_match(command)

    # 1) Restricted software: only block explicit run/execute; allow "write input", "analyze"
    run_like = re.search(r"\b(run|execute|exec|submit|invoke|call)\b", plan_lower)
    for sw, rule in RESTRICTED_SOFTWARE.items():
        if re.search(rule["pattern"], cmd_lower) or (sw in cmd_lower and run_like):
            # Allow remote submit and writing inputs
            if "remote" in plan_lower or "submit" in plan_lower or "mcp" in plan_lower:
                continue
            if "write" in plan_lower or "create" in plan_lower or "input" in plan_lower:
                if "run" not in plan_lower and "execute" not in plan_lower:
                    continue
            return False, f"Commercial/Restricted Software: {sw}", rule["suggestion"]

    # 2) Dangerous commands
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, command):
            return False, "System Security Risk", "The command contains potentially destructive or unsafe operations."

    return True, "", ""


def check_semantic_safety(plan: str) -> tuple[bool, str, str]:
    """
    Heuristic check for dual-use: allow academic/theoretical, deny practical synthesis/manufacturing.
    In production this can be replaced or augmented by a dedicated safety LLM.
    """
    plan_lower = _normalize_for_match(plan)

    sensitive_keywords = [
        "explosive", "detonation", "tnt", "rdx", "hmx", "cl-20", "petn", "energetic",
        "drug", "synthesis of", "synthesize", "recipe", "formulation", "manufacture",
        "make at home", "step-by-step synthesis", "preparation of", "how to make",
    ]
    allowed_intents = [
        "calculate", "simulation", "compute", "dft", "md", "property", "mechanism",
        "literature", "paper", "theory", "analysis", "crystal structure", "stability",
        "detonation velocity", "band gap", "phonon", "elastic", "ab initio",
    ]
    forbidden_intents = [
        "synthesis recipe", "synthesis procedure", "how to synthesize",
        "formulation ratio", "ingredient list", "manufacturing process",
        "weaponiz", "improvised", "at home", "household chemicals",
    ]

    has_sensitive = any(k in plan_lower for k in sensitive_keywords)
    has_forbidden = any(f in plan_lower for f in forbidden_intents)
    has_allowed = any(a in plan_lower for a in allowed_intents)

    if has_sensitive and has_forbidden and not has_allowed:
        return (
            False,
            "Safety/Ethics Restriction",
            "Requests for practical synthesis, manufacturing, or formulation details of sensitive materials are denied. Theoretical and computational research (DFT, MD, literature, properties) is allowed.",
        )

    return True, "", ""


def main() -> None:
    if len(sys.argv) < 2:
        _audit_denied("Invalid arguments", "Provide plan_description and intended_command.", "", "")
        out = {"allowed": False, "reason": "Invalid arguments", "suggestion": "Provide plan_description and intended_command (or one JSON object)."}
        print(json.dumps(out))
        sys.exit(1)

    plan = ""
    command = ""

    if len(sys.argv) == 2 and sys.argv[1].strip().startswith("{"):
        try:
            obj = json.loads(sys.argv[1])
            plan = obj.get("plan", "")
            command = obj.get("command", "")
        except json.JSONDecodeError:
            plan = sys.argv[1]
    else:
        plan = sys.argv[1] if len(sys.argv) > 1 else ""
        command = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    # 1) Hard rules
    allowed, reason, suggestion = check_hard_rules(plan, command)
    if not allowed:
        _audit_denied(reason, suggestion, plan, command)
        print(json.dumps({"allowed": False, "reason": reason, "suggestion": suggestion}))
        return

    # 2) Semantic safety
    allowed, reason, suggestion = check_semantic_safety(plan)
    if not allowed:
        _audit_denied(reason, suggestion, plan, command)
        print(json.dumps({"allowed": False, "reason": reason, "suggestion": suggestion}))
        return

    _audit_check(True, plan, command)
    print(json.dumps({"allowed": True, "reason": "Passed checks", "suggestion": ""}))


if __name__ == "__main__":
    main()
