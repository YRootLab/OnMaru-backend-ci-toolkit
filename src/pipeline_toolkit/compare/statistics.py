from __future__ import annotations
from statistics import median, quantiles

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
