#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from pipeline_toolkit.security.workflow_policy import validate_workflow_text

workflows = sorted(Path(".github/workflows").glob("*.yml")) + sorted(Path(".github/workflows").glob("*.yaml"))
violations = []
for workflow in workflows:
    for violation in validate_workflow_text(workflow.read_text()):
        violations.append(f"{workflow}: {violation}")
reusable = Path(".github/workflows/reusable-benchmark.yml")
if reusable.is_file():
    content = reusable.read_text()
    if "contents: read" not in content:
        violations.append(f"{reusable}: reusable workflow must declare contents: read")
    if "secrets." in content:
        violations.append(f"{reusable}: reusable workflow must not reference secrets")
module_benchmark = Path(".github/workflows/module-benchmark.yml")
if module_benchmark.is_file():
    content = module_benchmark.read_text()
    if "workflow_call:" not in content:
        violations.append(f"{module_benchmark}: module benchmark must declare workflow_call")
    if "contents: read" not in content:
        violations.append(f"{module_benchmark}: module benchmark must declare contents: read")
    if "secrets." in content:
        violations.append(f"{module_benchmark}: module benchmark must not reference secrets")
    if "pull_request_target" in content:
        violations.append(f"{module_benchmark}: module benchmark must not use pull_request_target")
    if "persist-credentials: false" not in content:
        violations.append(f"{module_benchmark}: checkouts must not persist credentials")
if violations:
    print("\n".join(violations), file=sys.stderr)
    raise SystemExit(1)
print(f"Workflow security verification passed ({len(workflows)} workflows).")
