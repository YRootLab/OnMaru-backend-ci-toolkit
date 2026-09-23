from pipeline_toolkit.compare.comparability import comparable
from pipeline_toolkit.reports.model import build_report

def test_mismatched_runner_conditions_are_inconclusive():
    result = comparable({"environment": "staging", "runner": "large"}, {"environment": "staging", "runner": "small"})
    assert result == {"comparable": False, "reason": "runner_mismatch"}

def test_report_contains_metric_and_artifact_provenance():
    report = build_report({"status": "regressed", "metrics": {"wall": 12}, "artifacts": [{"uri": "raw.json", "sha256": "abc"}]})
    assert report["status"] == "regressed"
    assert report["provenance"]["artifacts"][0]["uri"] == "raw.json"
