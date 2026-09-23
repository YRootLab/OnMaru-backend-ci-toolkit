from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Iterable, Sequence, Tuple

from pipeline_toolkit.contracts.module_evidence import (
    ModuleBenchmarkEvidence,
    validate_module_evidence,
)


class ComparisonClassification(str, Enum):
    COMPARABLE = "comparable"
    INCONCLUSIVE = "inconclusive"


class EvaluationTarget(str, Enum):
    PULL_REQUEST = "pull_request"
    RELEASE = "release"


ComparabilityKey = Tuple[str, ...]


@dataclass(frozen=True)
class ModuleBenchmarkComparison:
    classification: ComparisonClassification
    reason: str
    target: EvaluationTarget
    comparability_key: ComparabilityKey | None
    baseline_median: float | None
    candidate_median: float | None
    relative_delta: float | None
    policy_outcome: str


def module_benchmark_comparability_key(evidence: ModuleBenchmarkEvidence) -> ComparabilityKey:
    identity = evidence.environment_identity
    if identity is None:
        raise ValueError("environment_identity is required for comparison")
    provenance = evidence.provenance
    return (
        evidence.module_id,
        evidence.metric_name,
        evidence.unit,
        provenance.repository,
        provenance.workflow,
        provenance.job,
        identity.runner_image,
        identity.java_version,
        identity.python_version,
        identity.cache_state,
        identity.database_fixture,
        identity.cpu_memory_profile,
        identity.dependency_mode,
        identity.config_catalog_hash,
    )


def compare_module_benchmarks(
    baseline: Sequence[ModuleBenchmarkEvidence],
    candidate: Sequence[ModuleBenchmarkEvidence],
    *,
    target: EvaluationTarget,
) -> ModuleBenchmarkComparison:
    valid_baseline = _eligible_samples(baseline)
    valid_candidate = _eligible_samples(candidate)
    key = _shared_comparability_key(valid_baseline, valid_candidate)
    if key is None:
        return ModuleBenchmarkComparison(
            classification=ComparisonClassification.INCONCLUSIVE,
            reason="comparability_key_mismatch" if valid_baseline and valid_candidate else "no_valid_comparable_samples",
            target=target,
            comparability_key=None,
            baseline_median=None,
            candidate_median=None,
            relative_delta=None,
            policy_outcome="none",
        )

    baseline_median = median(item.metric_value for item in valid_baseline if item.metric_value is not None)
    candidate_median = median(item.metric_value for item in valid_candidate if item.metric_value is not None)
    relative_delta = None if baseline_median == 0 else (candidate_median - baseline_median) / baseline_median
    threshold = 0.15 if target is EvaluationTarget.RELEASE else 0.10
    return ModuleBenchmarkComparison(
        classification=ComparisonClassification.COMPARABLE,
        reason="comparable_samples",
        target=target,
        comparability_key=key,
        baseline_median=baseline_median,
        candidate_median=candidate_median,
        relative_delta=relative_delta,
        policy_outcome=("approval_hold" if target is EvaluationTarget.RELEASE else "warning")
        if relative_delta is not None and relative_delta > threshold
        else "none",
    )


def _eligible_samples(evidence: Iterable[ModuleBenchmarkEvidence]) -> list[ModuleBenchmarkEvidence]:
    selected = []
    for item in evidence:
        try:
            validate_module_evidence(item)
        except ValueError:
            continue
        if item.eligible_for_performance_sample:
            selected.append(item)
    return selected


def _shared_comparability_key(
    baseline: Sequence[ModuleBenchmarkEvidence], candidate: Sequence[ModuleBenchmarkEvidence]
) -> ComparabilityKey | None:
    keys = {module_benchmark_comparability_key(item) for item in [*baseline, *candidate]}
    return next(iter(keys)) if len(keys) == 1 and keys else None
