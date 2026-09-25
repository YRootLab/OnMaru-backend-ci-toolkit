from __future__ import annotations
from statistics import median, quantiles
from dataclasses import dataclass
from statistics import pvariance
from pipeline_toolkit.compare.comparability import comparable

@dataclass(frozen=True)
class ComparisonPolicy:
    warmup_runs: int = 0
    min_valid_runs: int = 2
    relative_threshold: float = .05
    absolute_threshold: float = 0

def compare_samples(baseline: list[float], candidate: list[float], relative_threshold: float = .05, absolute_threshold: float = 0, min_samples: int = 2) -> dict:
    if len(baseline) < min_samples or len(candidate) < min_samples:
        return {"status": "inconclusive", "reason": "insufficient_samples", "baseline_samples": len(baseline), "candidate_samples": len(candidate)}
    b, c = median(baseline), median(candidate); delta = c-b; relative = delta/b if b else None
    if relative is None: status = "inconclusive"
    elif abs(delta) <= absolute_threshold or abs(relative) <= relative_threshold: status = "unchanged"
    elif delta < 0: status = "improved"
    else: status = "regressed"
    result = {"status": status, "baseline_median": b, "candidate_median": c, "absolute_delta": delta, "relative_delta": relative, "baseline_samples": len(baseline), "candidate_samples": len(candidate)}
    if len(candidate) >= 4: result["candidate_p95"] = quantiles(candidate, n=20)[18]
    if len(baseline) >= 4: result["baseline_p95"] = quantiles(baseline, n=20)[18]
    return result

def compare_releases(baseline: list[float], candidate: list[float], baseline_conditions: dict, candidate_conditions: dict, *, policy: ComparisonPolicy = ComparisonPolicy(), baseline_run_ids: list[str] | None = None, candidate_run_ids: list[str] | None = None, baseline_artifacts: list[str] | None = None, candidate_artifacts: list[str] | None = None, baseline_resources: dict[str, float] | None = None, candidate_resources: dict[str, float] | None = None) -> dict:
    if not baseline: return {"status": "inconclusive", "reason": "no_baseline", "run_ids": list(candidate_run_ids or ())}
    if not candidate: return {"status": "inconclusive", "reason": "no_candidate", "run_ids": list(baseline_run_ids or ())}
    condition_result = comparable(baseline_conditions, candidate_conditions)
    if not condition_result["comparable"]: return {"status": "inconclusive", "reason": condition_result["reason"], "run_ids": [*(baseline_run_ids or ()), *(candidate_run_ids or ())]}
    b = baseline[policy.warmup_runs:]
    c = candidate[policy.warmup_runs:]
    if len(b) < policy.min_valid_runs or len(c) < policy.min_valid_runs:
        return {"status": "inconclusive", "reason": "insufficient_samples", "baseline_samples": len(b), "candidate_samples": len(c), "run_ids": [*(baseline_run_ids or ()), *(candidate_run_ids or ())]}
    result = compare_samples(b, c, policy.relative_threshold, policy.absolute_threshold, policy.min_valid_runs)
    result["run_ids"] = [*(baseline_run_ids or ()), *(candidate_run_ids or ())]
    result["artifact_uris"] = [*(baseline_artifacts or ()), *(candidate_artifacts or ())]
    result["baseline_variance"] = pvariance(b) if len(b) > 1 else None
    result["candidate_variance"] = pvariance(c) if len(c) > 1 else None
    result["resource_deltas"] = {key: candidate_resources[key] - baseline_resources[key] for key in sorted(set(baseline_resources or ()) & set(candidate_resources or ()))}
    return result
