from pipeline_toolkit.compare.statistics import ComparisonPolicy, compare_releases

def test_repeated_runs_report_median_p95_deltas_and_references():
    result = compare_releases(
        [10, 10, 11, 9, 10], [8, 8, 9, 7, 8],
        baseline_conditions={"environment": "staging", "runner": "large", "suite": "unit", "config_hash": "x", "cache": "warm", "fixture": "v1", "dependency_mode": "locked"},
        candidate_conditions={"environment": "staging", "runner": "large", "suite": "unit", "config_hash": "x", "cache": "warm", "fixture": "v1", "dependency_mode": "locked"},
        baseline_run_ids=["b1", "b2"], candidate_run_ids=["c1", "c2"], baseline_artifacts=["raw-b"], candidate_artifacts=["raw-c"],
        policy=ComparisonPolicy(min_valid_runs=3, relative_threshold=.05, absolute_threshold=.1),
    )
    assert result["status"] == "improved"
    assert result["baseline_median"] == 10
    assert "baseline_p95" in result and result["candidate_samples"] == 5
    assert result["run_ids"] == ["b1", "b2", "c1", "c2"]
    assert result["artifact_uris"] == ["raw-b", "raw-c"]

def test_no_baseline_mismatch_and_insufficient_samples_are_inconclusive():
    assert compare_releases([], [1, 2], {}, {})["reason"] == "no_baseline"
    assert compare_releases([1, 2], [1, 2], {"runner": "large"}, {"runner": "small"})["reason"] == "runner_mismatch"
    assert compare_releases([1], [2], {}, {}, policy=ComparisonPolicy(min_valid_runs=2))["reason"] == "insufficient_samples"

def test_resource_delta_is_reported_without_changing_latency_classification():
    result = compare_releases([10, 10], [10, 10], {}, {}, baseline_resources={"memory_mb": 100}, candidate_resources={"memory_mb": 125})
    assert result["status"] == "unchanged"
    assert result["resource_deltas"]["memory_mb"] == 25
