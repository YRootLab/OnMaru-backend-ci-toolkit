import pytest

from pipeline_toolkit.contracts.module_evidence import (
    EnvironmentIdentity,
    ModuleBenchmarkEvidence,
    ResourceUsage,
    RunProvenance,
    validate_module_evidence,
)


def _valid_evidence(**overrides):
    values = {
        "module_id": "catalog",
        "run_id": "run-20260923-001",
        "metric_name": "wall_clock_seconds",
        "metric_value": 12.5,
        "unit": "seconds",
        "resource": ResourceUsage(cpu_seconds=9.2, max_rss_bytes=1_048_576),
        "provenance": RunProvenance(
            repository="YRootLab/OnMaru-backend",
            commit_sha="a" * 40,
            workflow="verify",
            job="catalog",
        ),
        "environment_identity": EnvironmentIdentity(
            runner_image="ubuntu-24.04@sha256:runner",
            java_version="21.0.8",
            python_version="3.12.11",
            cache_state="warm",
            database_fixture="postgres-16.4-fixture-20260923",
            cpu_memory_profile="4cpu-16gb",
            dependency_mode="locked",
            config_catalog_hash="sha256:catalog",
        ),
        "artifact_uri": "artifact://github-actions/123/catalog-results.json",
    }
    values.update(overrides)
    return ModuleBenchmarkEvidence(**values)


def test_complete_successful_module_evidence_is_eligible_for_performance_samples():
    evidence = _valid_evidence()

    validate_module_evidence(evidence)

    assert evidence.eligible_for_performance_sample is True


def test_failed_module_evidence_is_ineligible_for_performance_samples():
    evidence = _valid_evidence(status="failed", metric_value=None)

    validate_module_evidence(evidence)

    assert evidence.eligible_for_performance_sample is False


def test_missing_artifact_evidence_is_ineligible_for_performance_samples():
    evidence = _valid_evidence(artifact_uri=None, complete=False)

    validate_module_evidence(evidence)

    assert evidence.eligible_for_performance_sample is False


def test_invalid_artifact_uri_is_rejected():
    evidence = _valid_evidence(artifact_uri="catalog-results.json")

    with pytest.raises(ValueError, match="artifact_uri"):
        validate_module_evidence(evidence)


def test_complete_successful_evidence_requires_a_metric_value():
    evidence = _valid_evidence(metric_value=None)

    with pytest.raises(ValueError, match="metric_value"):
        validate_module_evidence(evidence)


def test_complete_successful_evidence_requires_a_complete_environment_identity():
    evidence = _valid_evidence(environment_identity=None)

    with pytest.raises(ValueError, match="environment_identity"):
        validate_module_evidence(evidence)


def test_environment_identity_rejects_blank_required_field():
    evidence = _valid_evidence(
        environment_identity=EnvironmentIdentity(
            runner_image=" ",
            java_version="21.0.8",
            python_version="3.12.11",
            cache_state="warm",
            database_fixture="postgres-16.4-fixture-20260923",
            cpu_memory_profile="4cpu-16gb",
            dependency_mode="locked",
            config_catalog_hash="sha256:catalog",
        )
    )

    with pytest.raises(ValueError, match="environment_identity.runner_image"):
        validate_module_evidence(evidence)
