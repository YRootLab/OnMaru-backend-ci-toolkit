from __future__ import annotations

from dataclasses import dataclass
import re

from .model import ReleaseTrendManifest


@dataclass(frozen=True)
class BaselineSelection:
    manifest: ReleaseTrendManifest | None
    status: str
    reason: str
    strategy: str


def _conditions(manifest: ReleaseTrendManifest) -> tuple[str, str, str, str]:
    run = manifest.run
    return run.environment, run.suite, run.config_hash, run.runner_profile


def _version_key(tag: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", tag)
    return tuple(int(value or 0) for value in match.groups()) if match else (-1,)


def select_baseline(manifests: tuple[ReleaseTrendManifest, ...], candidate_tag: str, baseline: str) -> BaselineSelection:
    candidates = [item for item in manifests if item.release.tag == candidate_tag]
    if len(candidates) != 1: return BaselineSelection(None, "inconclusive", "candidate_not_found" if not candidates else "ambiguous_candidate_tag", baseline)
    candidate = candidates[0]
    if baseline != "previous":
        matches = [item for item in manifests if item.release.tag == baseline]
        if not matches: return BaselineSelection(None, "inconclusive", "baseline_not_found", "explicit")
        if len(matches) != 1: return BaselineSelection(None, "inconclusive", "ambiguous_baseline_tag", "explicit")
        selected = matches[0]
        if selected.release.commit_sha == candidate.release.commit_sha and selected.release.image_digest == candidate.release.image_digest:
            return BaselineSelection(None, "inconclusive", "baseline_matches_candidate", "explicit")
        if _conditions(selected) != _conditions(candidate):
            names = ("environment", "suite", "config", "runner")
            return BaselineSelection(None, "inconclusive", next(f"{name}_mismatch" for name, left, right in zip(names, _conditions(selected), _conditions(candidate)) if left != right), "explicit")
        if not selected.performance_eligible: return BaselineSelection(None, "inconclusive", "baseline_not_performance_eligible", "explicit")
        return BaselineSelection(selected, "selected", "matched_conditions", "explicit")
    comparable = [item for item in manifests if _version_key(item.release.tag) < _version_key(candidate_tag) and item.performance_eligible and _conditions(item) == _conditions(candidate)]
    if not comparable: return BaselineSelection(None, "inconclusive", "no_comparable_previous_release", "previous")
    return BaselineSelection(sorted(comparable, key=lambda item: _version_key(item.release.tag))[-1], "selected", "matched_conditions", "previous")
