from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from statistics import median
from typing import Iterable, Sequence, Tuple

from pipeline_toolkit.contracts.module_evidence import EvidenceStatus, ModuleBenchmarkEvidence, validate_module_evidence


class ComparisonClassification(str, Enum):
    COMPARABLE = "comparable"
    FAILED = "failed"
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
    comparability_reason: str
    baseline_identity: str | None
    baseline_median: float | None
    candidate_median: float | None
    relative_delta: float | None
    valid_baseline_samples: int
    valid_candidate_samples: int
    baseline_values: tuple[float, ...]
    candidate_values: tuple[float, ...]
    policy_threshold: float
    required_samples: int
    policy_outcome: str

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "reason": self.reason,
            "target": self.target.value,
            "comparability_key": list(self.comparability_key) if self.comparability_key else None,
            "comparability_reason": self.comparability_reason,
            "baseline_identity": self.baseline_identity,
            "baseline_median": self.baseline_median,
            "candidate_median": self.candidate_median,
            "relative_delta": self.relative_delta,
            "valid_sample_count": {"baseline": self.valid_baseline_samples, "candidate": self.valid_candidate_samples},
            "sample_values": {"baseline": list(self.baseline_values), "candidate": list(self.candidate_values)},
            "sample_range": {"baseline": _sample_range(self.baseline_values), "candidate": _sample_range(self.candidate_values)},
            "policy_threshold": self.policy_threshold,
            "required_samples": self.required_samples,
            "policy_outcome": self.policy_outcome,
        }


def module_benchmark_comparability_key(evidence: ModuleBenchmarkEvidence) -> ComparabilityKey:
    identity = evidence.environment_identity
    if identity is None:
        raise ValueError("environment_identity is required for comparison")
    provenance = evidence.provenance
    return (
        evidence.module_id, evidence.metric_name, evidence.unit, provenance.repository, provenance.workflow, provenance.job,
        identity.runner_image, identity.java_version, identity.python_version, identity.cache_state, identity.database_fixture,
        identity.cpu_memory_profile, identity.dependency_mode, identity.config_catalog_hash,
    )


def compare_module_benchmarks(baseline: Sequence[ModuleBenchmarkEvidence], candidate: Sequence[ModuleBenchmarkEvidence], *, target: EvaluationTarget) -> ModuleBenchmarkComparison:
    threshold, required_samples = _policy(target)
    valid_baseline = _eligible_samples(baseline)
    valid_candidate = _eligible_samples(candidate)
    key = _shared_comparability_key(valid_baseline, valid_candidate)
    if not valid_candidate and _all_failed(candidate):
        return _result(ComparisonClassification.FAILED, "candidate_evidence_failed", target, None, valid_baseline, valid_candidate, threshold, required_samples)
    if not valid_baseline and _all_failed(baseline):
        return _result(ComparisonClassification.FAILED, "baseline_evidence_failed", target, None, valid_baseline, valid_candidate, threshold, required_samples)
    if key is None:
        reason = "comparability_key_mismatch" if valid_baseline and valid_candidate else "no_valid_comparable_samples"
        return _result(ComparisonClassification.INCONCLUSIVE, reason, target, None, valid_baseline, valid_candidate, threshold, required_samples)
    if _has_duplicate_run_id(valid_baseline) or _has_duplicate_run_id(valid_candidate):
        return _result(ComparisonClassification.INCONCLUSIVE, "duplicate_run_id", target, key, valid_baseline, valid_candidate, threshold, required_samples)
    if len(valid_baseline) < required_samples or len(valid_candidate) < required_samples:
        return _result(ComparisonClassification.INCONCLUSIVE, "insufficient_valid_comparable_samples", target, key, valid_baseline, valid_candidate, threshold, required_samples)

    baseline_values = _sample_values(valid_baseline)
    candidate_values = _sample_values(valid_candidate)
    baseline_median = median(baseline_values)
    candidate_median = median(candidate_values)
    # Compare decimal interpretations of the input values while preserving the public numeric median fields.
    baseline_decimal = median(Decimal(str(value)) for value in baseline_values)
    candidate_decimal = median(Decimal(str(value)) for value in candidate_values)
    decimal_delta = None if baseline_decimal == 0 else (candidate_decimal - baseline_decimal) / baseline_decimal
    relative_delta = None if decimal_delta is None else float(decimal_delta)
    return ModuleBenchmarkComparison(
        classification=ComparisonClassification.COMPARABLE, reason="comparable_samples", target=target, comparability_key=key,
        comparability_reason="matched_comparability_key", baseline_identity=_baseline_identity(valid_baseline),
        baseline_median=baseline_median, candidate_median=candidate_median, relative_delta=relative_delta,
        valid_baseline_samples=len(valid_baseline), valid_candidate_samples=len(valid_candidate), policy_threshold=threshold,
        baseline_values=baseline_values, candidate_values=candidate_values,
        required_samples=required_samples, policy_outcome=_policy_outcome(target, decimal_delta, threshold),
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


def _shared_comparability_key(baseline: Sequence[ModuleBenchmarkEvidence], candidate: Sequence[ModuleBenchmarkEvidence]) -> ComparabilityKey | None:
    keys = {module_benchmark_comparability_key(item) for item in [*baseline, *candidate]}
    return next(iter(keys)) if len(keys) == 1 else None


def _all_failed(evidence: Sequence[ModuleBenchmarkEvidence]) -> bool:
    return bool(evidence) and all(item.status in (EvidenceStatus.FAILED, EvidenceStatus.FAILED.value) for item in evidence)


def _has_duplicate_run_id(evidence: Sequence[ModuleBenchmarkEvidence]) -> bool:
    return len({item.run_id for item in evidence}) != len(evidence)


def _sample_values(evidence: Sequence[ModuleBenchmarkEvidence]) -> tuple[float, ...]:
    return tuple(item.metric_value for item in evidence if item.metric_value is not None)


def _sample_range(values: tuple[float, ...]) -> float | None:
    return max(values) - min(values) if values else None


def _policy(target: EvaluationTarget) -> tuple[float, int]:
    return (0.15, 3) if target is EvaluationTarget.RELEASE else (0.10, 1)


def _policy_outcome(target: EvaluationTarget, relative_delta: Decimal | None, threshold: float) -> str:
    if relative_delta is None or relative_delta <= Decimal(str(threshold)):
        return "none"
    return "approval_hold" if target is EvaluationTarget.RELEASE else "warning"


def _baseline_identity(evidence: Sequence[ModuleBenchmarkEvidence]) -> str | None:
    identities = sorted({f"{item.provenance.repository}@{item.provenance.commit_sha}" for item in evidence})
    return ", ".join(identities) if identities else None


def _result(classification: ComparisonClassification, reason: str, target: EvaluationTarget, key: ComparabilityKey | None, baseline: Sequence[ModuleBenchmarkEvidence], candidate: Sequence[ModuleBenchmarkEvidence], threshold: float, required_samples: int) -> ModuleBenchmarkComparison:
    return ModuleBenchmarkComparison(
        classification=classification, reason=reason, target=target, comparability_key=key,
        comparability_reason="matched_comparability_key" if key else "comparability_key_unavailable",
        baseline_identity=_baseline_identity(baseline), baseline_median=None, candidate_median=None, relative_delta=None,
        valid_baseline_samples=len(baseline), valid_candidate_samples=len(candidate), policy_threshold=threshold,
        baseline_values=_sample_values(baseline), candidate_values=_sample_values(candidate),
        required_samples=required_samples, policy_outcome="none",
    )
