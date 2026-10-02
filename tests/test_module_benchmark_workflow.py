import json
import os
from pathlib import Path
import subprocess
import sys

import yaml
import pytest


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
        "longest_module_duration_seconds",
        "dag_critical_path_quality",
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
        "longest_module_duration_seconds",
        "dag_critical_path_quality",
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
    concurrency_group = workflow["jobs"]["module-test"]["concurrency"]["group"]
    assert "${{ matrix.id }}" in concurrency_group
    assert "${{ matrix.resource_profile }}" not in concurrency_group


def test_module_concurrency_is_isolated_per_workflow_run_and_attempt():
    module_job = load_workflow()["jobs"]["module-test"]

    assert module_job["concurrency"] == {
        "group": (
            "module-benchmark-${{ github.repository }}-${{ github.run_id }}-"
            "${{ github.run_attempt }}-${{ matrix.id }}"
        ),
        "cancel-in-progress": "false",
    }
    assert module_job["strategy"]["max-parallel"] == "${{ fromJSON(inputs.max_parallel) }}"


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
        json.dumps({"schema_version": 1, "run_id": 123, "run_attempt": 2, "toolkit_ref": "b" * 40,
                    "complete": True, "module_id": "api", "wall_clock_seconds": 4.5, "exit_code": 0})
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
        "WORKFLOW_STARTED_AT": "2026-10-01T00:00:00Z",
        "EXPECTED_MATRIX": json.dumps({"include": [{"id": "api"}]}),
        "TOOLKIT_REF": "b" * 40,
    }

    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True)

    lines = output_path.read_text().splitlines()
    assert len(lines) == 7
    assert dict(line.split("=", 1) for line in lines) == {
        "result": "inconclusive",
        "comparison_id": "123-2",
        "manifest_uri": "https://github.com/YRootLab/OnMaru-backend/actions/runs/123",
        "report_artifact": "module-benchmark-report",
        "critical_path_seconds": "",
        "longest_module_duration_seconds": "4.5",
        "dag_critical_path_quality": "unavailable",
    }
    report = (tmp_path / "module-benchmark-report" / "report.md").read_text()
    assert "\\n" not in report
    assert report.splitlines() == [
        "# Module benchmark",
        "",
        "Result: `inconclusive`",
        "",
        "Workflow wall-clock: `unavailable` seconds",
        "Longest module duration: `4.5` seconds",
        "DAG critical path: `unavailable`",
        "Sum of module work: `4.5` seconds",
        "Resource evidence: `unavailable`",
        "",
        "| Module | Wall-clock (s) | Exit |",
        "| --- | ---: | ---: |",
        "| api | 4.5 | 0 |",
    ]
    manifest = json.loads((tmp_path / "module-benchmark-report" / "manifest.json").read_text())
    assert manifest["critical_path_seconds"] is None
    assert manifest["dag_critical_path_quality"] == "unavailable"
    assert manifest["longest_module_duration_seconds"] == 4.5
    assert manifest["workflow_wall_clock_seconds"] is None
    assert manifest["workflow_wall_clock_quality"] == "unavailable"


def test_aggregate_report_exposes_wall_clock_work_and_monitoring_fields():
    text = WORKFLOW.read_text()

    assert '"workflow_wall_clock_seconds"' in text
    assert '"sum_work_seconds"' in text
    assert '"resource_evidence"' in text
    assert "| Module | Wall-clock (s) | Exit |" in text
    assert "Workflow wall-clock" in text


def test_module_producer_emits_versioned_attempt_evidence_joinable_by_explicit_job_mapping(tmp_path):
    import hashlib
    from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline
    step = next(step for step in load_workflow()["jobs"]["module-test"]["steps"] if step.get("id") == "test")
    script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    root = tmp_path / ".module-benchmark" / "api"
    root.mkdir(parents=True)
    (root / "time.txt").write_text("Elapsed (wall clock) time (h:mm:ss or m:ss): 0:06.00\n")
    env = os.environ | {"MODULE_ID": "api", "TEST_COMMAND": "echo harmless", "MODULE_EXIT_STATUS": "1",
                        "MODULE_STARTED_AT": "2026-10-01T00:00:02Z", "MODULE_ENDED_AT": "2026-10-01T00:00:08Z",
                        "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2", "TOOLKIT_REF": "b" * 40}
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True)
    payload = (root / "execution.json").read_bytes()
    produced = json.loads(payload)
    assert produced["schema_version"] == 1
    assert produced["run_id"] == 42
    assert produced["run_attempt"] == 2
    assert produced["toolkit_ref"] == "b" * 40
    timeline = normalize_actions_timeline(
        {"id": 42, "run_attempt": 2}, {"total_count": 1, "jobs": [{"id": 701, "steps": []}]},
        toolkit_ref="b" * 40, expected_modules={"api": 701},
        module_artifacts=[{"id": 91, "data": payload, "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}])
    assert timeline["artifact_quality"]["status"] == "complete"
    assert timeline["modules"][0]["job_id"] == 701
    assert timeline["modules"][0]["status"] == "failed"
    assert "command" not in timeline["modules"][0]


def test_aggregate_does_not_replace_unknown_module_duration_with_zero(tmp_path):
    summary = next(step for step in load_workflow()["jobs"]["aggregate"]["steps"] if step.get("id") == "summary")
    script = summary["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    evidence = tmp_path / "module-evidence" / "module-evidence-api"
    evidence.mkdir(parents=True)
    (evidence / "execution.json").write_text(json.dumps({"schema_version": 1, "run_id": 42, "run_attempt": 2,
        "toolkit_ref": "b" * 40, "complete": False, "module_id": "api", "wall_clock_seconds": None, "exit_code": 1}))
    (tmp_path / "module-benchmark-report").mkdir()
    env = os.environ | {"MATRIX_RESULT": "failure", "DETECT_RESULT": "success", "MODE": "pr", "BASELINE_REF": "develop",
                        "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SERVER_URL": "https://github.com",
                        "GITHUB_REPOSITORY": "example/backend", "GITHUB_OUTPUT": str(tmp_path / "github-output"),
                        "EXPECTED_MATRIX": json.dumps({"include": [{"id": "api"}]}), "TOOLKIT_REF": "b" * 40}
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True)
    manifest = json.loads((tmp_path / "module-benchmark-report/manifest.json").read_text())
    assert manifest["longest_module_duration_seconds"] is None
    assert manifest["longest_module_duration_quality"] == "unavailable"
    assert manifest["sum_work_quality"] == "partial"
    assert "Longest module duration: `unavailable`" in (tmp_path / "module-benchmark-report/report.md").read_text()


@pytest.mark.parametrize("case, expected_duration, quality", [
    ("missing", 4.5, "partial"), ("stale_attempt", None, "unavailable"),
    ("foreign_run", None, "unavailable"), ("duplicate", None, "unavailable"),
    ("unexpected", None, "unavailable"), ("invalid_matrix", None, "unavailable"),
])
def test_aggregate_validates_expected_matrix_and_current_run_attempt(tmp_path, case, expected_duration, quality):
    summary = next(step for step in load_workflow()["jobs"]["aggregate"]["steps"] if step.get("id") == "summary")
    script = summary["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    root = tmp_path / "module-evidence/module-evidence-api"
    root.mkdir(parents=True)
    record = {"schema_version": 1, "run_id": 42, "run_attempt": 2, "toolkit_ref": "b" * 40,
              "complete": True, "module_id": "api", "wall_clock_seconds": 4.5, "exit_code": 0}
    if case == "stale_attempt":
        record["run_attempt"] = 1
    elif case == "foreign_run":
        record["run_id"] = 41
    elif case == "unexpected":
        record["module_id"] = "other"
    (root / "execution.json").write_text(json.dumps(record))
    if case == "duplicate":
        second = tmp_path / "module-evidence/duplicate"
        second.mkdir()
        (second / "execution.json").write_text(json.dumps(record))
    (tmp_path / "module-benchmark-report").mkdir()
    expected = {"include": [{"id": "api"}, {"id": "worker"}]} if case == "missing" else {"include": [{"id": "api"}]}
    env = os.environ | {"MATRIX_RESULT": "success", "DETECT_RESULT": "success", "MODE": "pr", "BASELINE_REF": "develop",
        "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "example/backend", "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        "EXPECTED_MATRIX": "invalid" if case == "invalid_matrix" else json.dumps(expected), "TOOLKIT_REF": "b" * 40}
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True)
    manifest = json.loads((tmp_path / "module-benchmark-report/manifest.json").read_text())
    assert manifest["longest_module_duration_seconds"] == expected_duration
    assert manifest["longest_module_duration_quality"] == quality
    assert manifest["sum_work_quality"] == "partial"
    assert manifest["quality"]["issues"]
    if case != "missing":
        assert manifest["executions"] == []
    else:
        assert "missing_module:worker" in manifest["quality"]["issues"]
    report = (tmp_path / "module-benchmark-report/report.md").read_text()
    assert "Quality issues" in report
