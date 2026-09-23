from __future__ import annotations

from dataclasses import replace

import pytest

from pipeline_toolkit.compare.module_benchmark import (
    ComparisonClassification,
    EvaluationTarget,
    compare_module_benchmarks,
    module_benchmark_comparability_key,
)
from pipeline_toolkit.contracts.module_evidence import (
    EnvironmentIdentity,
    ModuleBenchmarkEvidence,
    ResourceUsage,
    RunProvenance,
)


def _evidence(*, run_id: str, value: float, identity: EnvironmentIdentity | None = None):
    return ModuleBenchmarkEvidence(
        module_id="catalog",
        run_id=run_id,
        metric_name="wall_clock_seconds",
        metric_value=value,
        unit="seconds",
        resource=ResourceUsage(cpu_seconds=4.0),
        provenance=RunProvenance(
            repository="YRootLab/OnMaru-backend",
            commit_sha="a" * 40,
            workflow="verify",
            job="catalog",
        ),
        environment_identity=identity or EnvironmentIdentity(
            runner_image="ubuntu-24.04@sha256:runner",
            java_version="21.0.8",
            python_version="3.12.11",
            cache_state="warm",
            database_fixture="postgres-16.4-fixture-20260923",
            cpu_memory_profile="4cpu-16gb",
            dependency_mode="locked",
            config_catalog_hash="sha256:catalog",
        ),
        artifact_uri=f"artifact://github-actions/{run_id}/result.json",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("runner_image", "ubuntu-22.04@sha256:runner"),
        ("java_version", "17.0.16"),
        ("python_version", "3.11.13"),
        ("cache_state", "cold"),
        ("database_fixture", "postgres-17.0-fixture-20260923"),
        ("cpu_memory_profile", "2cpu-8gb"),
        ("dependency_mode", "floating"),
        ("config_catalog_hash", "sha256:other-catalog"),
    ],
)
def test_any_environment_identity_mismatch_is_inconclusive(field, value):
    baseline = _evidence(run_id="base", value=100)
    candidate = _evidence(
        run_id="candidate",
        value=111,
        identity=replace(baseline.environment_identity, **{field: value}),
    )

    result = compare_module_benchmarks(
        [baseline], [candidate], target=EvaluationTarget.PULL_REQUEST
    )

    assert result.classification is ComparisonClassification.INCONCLUSIVE
    assert result.reason == "comparability_key_mismatch"


def test_matching_environment_identity_retains_pr_warning_policy_calculation():
    baseline = _evidence(run_id="base", value=100)
    candidate = _evidence(run_id="candidate", value=111)

    result = compare_module_benchmarks(
        [baseline], [candidate], target=EvaluationTarget.PULL_REQUEST
    )

    assert result.classification is ComparisonClassification.COMPARABLE
    assert result.policy_outcome == "warning"
    assert result.relative_delta == 0.11
    assert len(module_benchmark_comparability_key(baseline)) == 14
