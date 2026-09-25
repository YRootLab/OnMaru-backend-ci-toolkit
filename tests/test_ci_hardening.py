from pathlib import Path

def test_ci_uses_pinned_test_dependencies_and_coverage_gate():
    requirements = Path("requirements-ci.txt").read_text()
    workflow = Path(".github/workflows/ci.yml").read_text()
    assert "pytest==" in requirements and "coverage==" in requirements
    assert "python -m coverage report" in workflow or "coverage report" in Path("scripts/verify_toolkit.sh").read_text()

def test_reusable_workflow_accepts_only_workflow_call_triggers_without_caller_event_guard():
    workflow = Path(".github/workflows/reusable-benchmark.yml").read_text()
    assert "workflow_call:" in workflow
    assert "github.event_name == 'workflow_call'" not in workflow
    assert "with: {" not in workflow


def test_release_please_bootstraps_the_same_pinned_python_dependencies_before_verification():
    workflow = Path(".github/workflows/release-please.yml").read_text()
    setup = workflow.index("actions/setup-python@v5")
    install = workflow.index("python -m pip install --disable-pip-version-check -r requirements-ci.txt")
    verify = workflow.index("./scripts/verify_toolkit.sh")

    assert "python-version: '3.11'" in workflow
    assert setup < install < verify
