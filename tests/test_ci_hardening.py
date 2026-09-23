from pathlib import Path

def test_ci_uses_pinned_test_dependencies_and_coverage_gate():
    requirements = Path("requirements-ci.txt").read_text()
    workflow = Path(".github/workflows/ci.yml").read_text()
    assert "pytest==" in requirements and "coverage==" in requirements
    assert "python -m coverage report" in workflow or "coverage report" in Path("scripts/verify_toolkit.sh").read_text()

def test_reusable_workflow_is_safe_when_directly_triggered_by_repository_events():
    workflow = Path(".github/workflows/reusable-benchmark.yml").read_text()
    assert "github.event_name == 'workflow_call'" in workflow
    assert "with: {" not in workflow
