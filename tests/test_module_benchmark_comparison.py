from __future__ import annotations

from dataclasses import replace
import json

import pytest

from pipeline_toolkit.compare.module_benchmark import ComparisonClassification, EvaluationTarget, compare_module_benchmarks, module_benchmark_comparability_key
from pipeline_toolkit.contracts.module_evidence import EvidenceStatus, EnvironmentIdentity, ModuleBenchmarkEvidence, ResourceUsage, RunProvenance
from pipeline_toolkit.reports.module_benchmark import render_module_benchmark_json, render_module_benchmark_markdown


def _evidence(*, run_id: str, value: float | None, commit: str = "a" * 40, status=EvidenceStatus.SUCCESS, complete=True, job="catalog", identity: EnvironmentIdentity | None = None):
    return ModuleBenchmarkEvidence(
        module_id="catalog", run_id=run_id, metric_name="wall_clock_seconds", metric_value=value, unit="seconds",
        resource=ResourceUsage(cpu_seconds=4.0),
        provenance=RunProvenance(repository="YRootLab/OnMaru-backend", commit_sha=commit, workflow="verify", job=job),
        environment_identity=identity or EnvironmentIdentity(
            runner_image="ubuntu-24.04@sha256:runner", java_version="21.0.8", python_version="3.12.11", cache_state="warm",
            database_fixture="postgres-16.4-fixture-20260923", cpu_memory_profile="4cpu-16gb", dependency_mode="locked", config_catalog_hash="sha256:catalog",
        ),
        artifact_uri=f"artifact://github-actions/{run_id}/result.json", status=status, complete=complete,
    )


@pytest.mark.parametrize("field,value", [("runner_image", "ubuntu-22.04@sha256:runner"), ("java_version", "17.0.16"), ("python_version", "3.11.13"), ("cache_state", "cold"), ("database_fixture", "postgres-17.0-fixture-20260923"), ("cpu_memory_profile", "2cpu-8gb"), ("dependency_mode", "floating"), ("config_catalog_hash", "sha256:other-catalog")])
def test_environment_identity_mismatch_is_inconclusive(field, value):
    baseline = _evidence(run_id="base", value=100)
    candidate = _evidence(run_id="candidate", value=111, identity=replace(baseline.environment_identity, **{field: value}))

    result = compare_module_benchmarks([baseline], [candidate], target=EvaluationTarget.PULL_REQUEST)

    assert result.classification is ComparisonClassification.INCONCLUSIVE
    assert result.reason == "comparability_key_mismatch"


def test_pr_regression_is_comparable_warning_and_excludes_failed_samples():
    baseline = [_evidence(run_id=f"base-{index}", value=100) for index in range(2)]
    candidate = [_evidence(run_id=f"candidate-{index}", value=111, commit="b" * 40) for index in range(2)] + [_evidence(run_id="failed", value=None, commit="b" * 40, status=EvidenceStatus.FAILED)]

    result = compare_module_benchmarks(baseline, candidate, target=EvaluationTarget.PULL_REQUEST)

    assert result.classification is ComparisonClassification.COMPARABLE
    assert result.policy_outcome == "warning"
    assert result.valid_baseline_samples == result.valid_candidate_samples == 2
    assert result.relative_delta == 0.11
    assert len(module_benchmark_comparability_key(baseline[0])) == 14


def test_release_hold_requires_five_valid_comparable_samples():
    baseline = [_evidence(run_id=f"base-{index}", value=100) for index in range(5)]
    candidate = [_evidence(run_id=f"candidate-{index}", value=116, commit="b" * 40) for index in range(5)]

    result = compare_module_benchmarks(baseline, candidate, target=EvaluationTarget.RELEASE)

    assert result.classification is ComparisonClassification.COMPARABLE
    assert result.policy_outcome == "approval_hold"
    assert result.policy_threshold == 0.15
    assert result.required_samples == 5


def test_release_regression_with_fewer_than_five_samples_is_inconclusive_not_held():
    result = compare_module_benchmarks(
        [_evidence(run_id=f"base-{index}", value=100) for index in range(4)],
        [_evidence(run_id=f"candidate-{index}", value=116, commit="b" * 40) for index in range(4)],
        target=EvaluationTarget.RELEASE,
    )

    assert result.classification is ComparisonClassification.INCONCLUSIVE
    assert result.reason == "insufficient_valid_comparable_samples"
    assert result.policy_outcome == "none"


def test_only_failed_candidate_evidence_is_classified_as_failed():
    result = compare_module_benchmarks([_evidence(run_id="base", value=100)], [_evidence(run_id="candidate", value=None, commit="b" * 40, status=EvidenceStatus.FAILED)], target=EvaluationTarget.PULL_REQUEST)

    assert result.classification is ComparisonClassification.FAILED
    assert result.reason == "candidate_evidence_failed"


def test_json_and_markdown_reports_include_policy_sample_and_baseline_identity():
    result = compare_module_benchmarks([_evidence(run_id="base", value=100)], [_evidence(run_id="candidate", value=111, commit="b" * 40)], target=EvaluationTarget.PULL_REQUEST)

    payload = json.loads(render_module_benchmark_json(result))
    markdown = render_module_benchmark_markdown(result)

    assert payload["policy_threshold"] == 0.10
    assert payload["valid_sample_count"] == {"baseline": 1, "candidate": 1}
    assert payload["baseline_identity"] == "YRootLab/OnMaru-backend@" + "a" * 40
    assert payload["comparability_reason"] == "matched_comparability_key"
    assert "Policy threshold: `10%`" in markdown
    assert "Baseline identity: `YRootLab/OnMaru-backend@" + "a" * 40 + "`" in markdown
