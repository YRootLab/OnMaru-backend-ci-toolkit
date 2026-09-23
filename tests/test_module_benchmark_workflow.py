from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/module-benchmark.yml")


def load_workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_reusable_module_benchmark_declares_prd_workflow_call_contract():
    workflow = load_workflow()

    contract = workflow["on"]["workflow_call"]
    assert set(contract["inputs"]) == {
        "catalog_path",
        "mode",
        "max_parallel",
        "baseline_ref",
        "comment_mode",
    }
    assert contract["inputs"]["catalog_path"]["type"] == "string"
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
    assert "module-benchmark-${{ github.repository }}-${{ matrix.resource_profile }}" in text
