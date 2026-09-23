from __future__ import annotations
import re

def validate_workflow_text(text: str) -> list[str]:
    violations: list[str] = []
    has_pull_request = bool(re.search(r"^\s*pull_request\s*:", text, re.MULTILINE))
    if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
        violations.append("pull_request_target_is_not_allowed")
    if has_pull_request:
        contents = re.search(r"^\s*contents\s*:\s*([^\s#]+)", text, re.MULTILINE)
        if not contents or contents.group(1) != "read":
            violations.append("pull_request_requires_read_only_contents")
        if re.search(r"\$\{\{\s*secrets\.", text) or re.search(r"\bsecrets\.[A-Za-z_][A-Za-z0-9_]*", text):
            violations.append("fork_workflow_must_not_reference_secrets")
    return violations
