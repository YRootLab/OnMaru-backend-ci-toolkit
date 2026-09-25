from __future__ import annotations

from pipeline_toolkit.compare.statistics import compare_releases

from .model import ReleaseTrendManifest
from .selector import select_baseline


def compare_metric(manifests: tuple[ReleaseTrendManifest, ...], candidate_tag: str, baseline: str, metric_id: str) -> dict:
    selection = select_baseline(manifests, candidate_tag, baseline)
    if selection.manifest is None: return {"status": "inconclusive", "reason": selection.reason, "baseline_strategy": selection.strategy}
    candidate = next(item for item in manifests if item.release.tag == candidate_tag)
    lookup = lambda manifest: next((metric for metric in manifest.metrics if metric.id == metric_id), None)
    baseline_metric, candidate_metric = lookup(selection.manifest), lookup(candidate)
    if baseline_metric is None or candidate_metric is None: return {"status": "inconclusive", "reason": "metric_not_found", "baseline_strategy": selection.strategy}
    result = compare_releases(list(baseline_metric.samples), list(candidate_metric.samples), {}, {})
    result.update({"baseline_strategy": selection.strategy, "baseline_release": {"tag": selection.manifest.release.tag, "commit_sha": selection.manifest.release.commit_sha, "image_digest": selection.manifest.release.image_digest}, "candidate_release": {"tag": candidate.release.tag, "commit_sha": candidate.release.commit_sha, "image_digest": candidate.release.image_digest}, "metric": metric_id, "unit": candidate_metric.unit})
    return result
