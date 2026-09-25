from pipeline_toolkit.trend.model import ReleaseTrendManifest, TrendMetric, TrendRelease, TrendRun
from pipeline_toolkit.trend.selector import select_baseline


def manifest(tag, sha, *, environment="staging", status="success", samples=(10.0, 11.0)):
    return ReleaseTrendManifest(TrendRelease("repo", tag, sha * 40, "sha256:" + "d" * 64), TrendRun(f"run-{tag}", status, environment, "suite", "config", "runner", "0.1", "https://example.com/a"), (TrendMetric("pipeline.wall_clock", "seconds", samples),))


def test_previous_selects_nearest_earlier_comparable_success():
    candidate = manifest("v1.4.0", "d")
    selected = select_baseline((manifest("v1.1.0", "a"), manifest("v1.2.0", "b", environment="prod"), manifest("v1.3.0", "c"), candidate), candidate.release.tag, "previous")
    assert selected.manifest.release.tag == "v1.3.0"
    assert selected.status == "selected"


def test_explicit_incompatible_or_missing_baseline_is_inconclusive():
    candidate = manifest("v1.4.0", "d")
    incompatible = manifest("v1.3.0", "c", environment="prod")
    selection = select_baseline((incompatible, candidate), "v1.4.0", "v1.3.0")
    assert selection.manifest is None
    assert selection.reason == "environment_mismatch"
    assert select_baseline((candidate,), "v1.4.0", "v1.1.0").reason == "baseline_not_found"


def test_failed_and_duplicate_identity_are_never_selected():
    candidate = manifest("v1.4.0", "d")
    assert select_baseline((manifest("v1.3.0", "c", status="failed", samples=()), candidate), "v1.4.0", "previous").reason == "no_comparable_previous_release"
    duplicate = manifest("v1.3.0", "e")
    assert select_baseline((manifest("v1.3.0", "c"), duplicate, candidate), "v1.4.0", "v1.3.0").reason == "ambiguous_baseline_tag"


def test_previous_uses_semantic_version_order_and_rejects_candidate_as_baseline():
    candidate = manifest("v1.11.0", "d")
    selected = select_baseline((manifest("v1.9.0", "a"), manifest("v1.10.0", "b"), candidate), candidate.release.tag, "previous")
    assert selected.manifest.release.tag == "v1.10.0"
    assert select_baseline((candidate,), candidate.release.tag, candidate.release.tag).reason == "baseline_matches_candidate"
