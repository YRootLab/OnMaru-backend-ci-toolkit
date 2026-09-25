from pipeline_toolkit.trend.service import compare_metric
from tests.test_trend_selector import manifest


def test_compare_metric_reuses_statistics_only_after_selection():
    result = compare_metric((manifest("v1.3.0", "c"), manifest("v1.4.0", "d", samples=(8.0, 9.0))), "v1.4.0", "previous", "pipeline.wall_clock")
    assert result["status"] == "improved"
    assert result["baseline_release"]["tag"] == "v1.3.0"


def test_compare_metric_preserves_inconclusive_reason():
    result = compare_metric((manifest("v1.4.0", "d"),), "v1.4.0", "previous", "pipeline.wall_clock")
    assert result == {"status": "inconclusive", "reason": "no_comparable_previous_release", "baseline_strategy": "previous"}
