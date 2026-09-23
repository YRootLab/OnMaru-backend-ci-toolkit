import json
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


def _run_module_plan(catalog: Path, *changed_paths: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {"PYTHONPATH": str(REPOSITORY_ROOT / "src")}
    command = [
        sys.executable,
        "-m",
        "pipeline_toolkit.cli",
        "module-plan",
        "--catalog",
        str(catalog),
    ]
    for changed_path in changed_paths:
        command.extend(("--changed-path", changed_path))
    return subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment, text=True, capture_output=True, check=False)


def _catalog(tmp_path: Path) -> Path:
    catalog = tmp_path / "modules.yml"
    catalog.write_text(
        json.dumps(
            {
                "version": 1,
                "modules": [
                    {"id": "web", "paths": ["web/**"], "depends_on": ["api"], "test_command": "test-web", "resource_profile": "standard"},
                    {"id": "api", "paths": ["api/**"], "depends_on": [], "test_command": "test-api", "resource_profile": "standard"},
                ],
                "always_full_paths": [".github/**"],
            }
        )
    )
    return catalog


def test_module_plan_emits_deterministic_affected_matrix_json(tmp_path: Path):
    result = _run_module_plan(_catalog(tmp_path), "api/routes.py")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == json.dumps(
        {
            "full_suite": False,
            "modules": [
                {"depends_on": [], "id": "api", "paths": ["api/**"], "resource_profile": "standard", "test_command": "test-api"},
                {"depends_on": ["api"], "id": "web", "paths": ["web/**"], "resource_profile": "standard", "test_command": "test-web"},
            ],
            "reason": "affected",
            "version": 1,
        },
        sort_keys=True,
    ) + "\n"


def test_module_plan_uses_full_suite_for_unavailable_diff(tmp_path: Path):
    result = _run_module_plan(_catalog(tmp_path))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["full_suite"] is True
    assert json.loads(result.stdout)["reason"] == "unknown-diff"


def test_module_plan_uses_full_suite_for_unknown_path(tmp_path: Path):
    result = _run_module_plan(_catalog(tmp_path), "unmapped/file.txt")

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["full_suite"] is True
    assert json.loads(result.stdout)["reason"] == "unknown-path"


def test_module_plan_reports_invalid_catalog_on_stderr(tmp_path: Path):
    catalog = tmp_path / "invalid.yml"
    catalog.write_text("version: 99\nmodules: []\n")

    result = _run_module_plan(catalog, "api/routes.py")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "module-plan: invalid module catalog: module catalog version must be 1\n"
