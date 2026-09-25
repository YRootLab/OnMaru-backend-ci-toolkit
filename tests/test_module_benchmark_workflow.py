import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


WORKFLOW = Path(".github/workflows/module-benchmark.yml")


def load_workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_reusable_module_benchmark_declares_prd_workflow_call_contract():
    workflow = load_workflow()

    contract = workflow["on"]["workflow_call"]
    assert set(contract["inputs"]) == {
        "catalog_path",
        "toolkit_ref",
        "mode",
        "max_parallel",
        "baseline_ref",
        "comment_mode",
    }
    assert contract["inputs"]["catalog_path"]["type"] == "string"
    assert contract["inputs"]["toolkit_ref"] == {
        "description": "Immutable 40-character lowercase toolkit commit SHA supplied by the caller.",
        "required": "true",
        "type": "string",
    }
    assert contract["inputs"]["mode"]["default"] == "pr"
    assert contract["inputs"]["max_parallel"]["type"] == "number"
    assert set(contract["outputs"]) == {
        "result",
        "comparison_id",
        "manifest_uri",
        "report_artifact",
        "critical_path_seconds",
    }


def test_workflow_preserves_detect_matrix_aggregate_verify_fan_in_contract():
    jobs = load_workflow()["jobs"]

    assert set(jobs) == {"detect", "module-test", "aggregate", "verify"}
    assert jobs["module-test"]["needs"] == "detect"
    assert jobs["module-test"]["strategy"]["fail-fast"] == "false"
    assert jobs["module-test"]["strategy"]["max-parallel"] == "${{ fromJSON(inputs.max_parallel) }}"
    assert jobs["aggregate"]["needs"] == ["detect", "module-test"]
    assert jobs["aggregate"]["if"] == "${{ always() }}"
    assert jobs["verify"]["needs"] == "aggregate"
    assert jobs["verify"]["if"] == "${{ always() }}"
    assert set(jobs["verify"]["outputs"]) == {
        "result",
        "comparison_id",
        "manifest_uri",
        "report_artifact",
        "critical_path_seconds",
    }


def test_workflow_is_read_only_secret_free_and_publishes_evidence_artifacts():
    text = WORKFLOW.read_text()
    workflow = load_workflow()

    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in text
    assert "pull_request_target" not in text
    assert "persist-credentials: false" in text
    assert "actions/upload-artifact@v4" in text
    assert "actions/download-artifact@v4" in text
    assert "module-evidence-${{ matrix.id }}" in text
    assert "module-benchmark-report" in text
    assert "module-benchmark-${{ github.repository }}-${{ matrix.id }}" in text
    assert "module-benchmark-${{ github.repository }}-${{ matrix.resource_profile }}" not in text


def test_cross_repository_caller_pins_toolkit_checkout_to_its_explicit_immutable_ref():
    workflow = load_workflow()
    text = WORKFLOW.read_text()

    caller_contract = {
        "repository": "YRootLab/OnMaru-backend",
        "toolkit_ref": "d8d67b3102164e0fa340322bef1d3f1d9b081153",
    }
    assert caller_contract["repository"] != "YRootLab/OnMaru-backend-ci-toolkit"
    assert len(caller_contract["toolkit_ref"]) == 40
    assert caller_contract["toolkit_ref"].islower()

    detect_steps = workflow["jobs"]["detect"]["steps"]
    validation = detect_steps[0]
    toolkit_checkout = next(
        step for step in detect_steps if step["name"] == "Checkout immutable toolkit implementation"
    )

    assert validation["env"]["TOOLKIT_REF"] == "${{ inputs.toolkit_ref }}"
    assert '[[ "$TOOLKIT_REF" =~ ^[0-9a-f]{40}$ ]]' in validation["run"]
    assert toolkit_checkout["with"]["repository"] == "YRootLab/OnMaru-backend-ci-toolkit"
    assert toolkit_checkout["with"]["ref"] == "${{ inputs.toolkit_ref }}"
    assert "github.workflow_sha" not in text


def test_aggregate_script_writes_separate_outputs_and_rendered_report(tmp_path):
    steps = load_workflow()["jobs"]["aggregate"]["steps"]
    summary = next(step for step in steps if step.get("id") == "summary")
    script = summary["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]

    evidence = tmp_path / "module-evidence" / "module-evidence-api"
    evidence.mkdir(parents=True)
    (evidence / "execution.json").write_text(
        json.dumps({"module_id": "api", "wall_clock_seconds": 4.5, "exit_code": 0})
    )
    (tmp_path / "module-benchmark-report").mkdir()
    output_path = tmp_path / "github-output"
    env = os.environ | {
        "MATRIX_RESULT": "success",
        "DETECT_RESULT": "success",
        "MODE": "pr",
        "BASELINE_REF": "develop",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "YRootLab/OnMaru-backend",
        "GITHUB_OUTPUT": str(output_path),
    }

    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True)

    lines = output_path.read_text().splitlines()
    assert len(lines) == 5
    assert dict(line.split("=", 1) for line in lines) == {
        "result": "inconclusive",
        "comparison_id": "123-2",
        "manifest_uri": "https://github.com/YRootLab/OnMaru-backend/actions/runs/123",
        "report_artifact": "module-benchmark-report",
        "critical_path_seconds": "4.5",
    }
    report = (tmp_path / "module-benchmark-report" / "report.md").read_text()
    assert "\\n" not in report
    assert report.splitlines() == [
        "# Module benchmark",
        "",
        "Result: `inconclusive`",
        "",
        "Critical path: `4.5` seconds",
    ]
