from pipeline_toolkit.trend.service import compare_metric
from tests.test_trend_selector import manifest


def test_compare_metric_reuses_statistics_only_after_selection():
    result = compare_metric((manifest("v1.3.0", "c"), manifest("v1.4.0", "d", samples=(8.0, 9.0))), "v1.4.0", "previous", "pipeline.wall_clock")
    assert result["status"] == "improved"
    assert result["baseline_release"]["tag"] == "v1.3.0"


def test_compare_metric_preserves_inconclusive_reason():
    result = compare_metric((manifest("v1.4.0", "d"),), "v1.4.0", "previous", "pipeline.wall_clock")
    assert result == {"status": "inconclusive", "reason": "no_comparable_previous_release", "baseline_strategy": "previous"}


def test_history_orders_observations_by_semantic_version():
    from pipeline_toolkit.trend.service import history_metric
    result = history_metric((manifest("v1.10.0", "a"), manifest("v1.9.0", "b"), manifest("v1.11.0", "c")), "v1.11.0", "pipeline.wall_clock", 3)
    assert [item["tag"] for item in result["observations"]] == ["v1.9.0", "v1.10.0", "v1.11.0"]
