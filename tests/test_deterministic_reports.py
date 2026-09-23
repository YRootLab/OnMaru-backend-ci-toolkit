import base64
from pipeline_toolkit.reports.model import build_report, top_n, paginate
from pipeline_toolkit.reports.render import render_job_summary, render_png

def test_report_keeps_runtime_metrics_quality_and_release_context():
    report = build_report({
        "status": "inconclusive",
        "baseline": {"tag": "v1", "commit_sha": "a"},
        "candidate": {"tag": "v2", "commit_sha": "b"},
        "metrics": {"wall_clock_seconds": 10, "work_seconds": 15, "critical_path_seconds": 8},
        "samples": {"baseline": 1, "candidate": 2},
        "quality": "partial",
        "artifacts": [{"uri": "raw.json", "sha256": "abc"}],
    })
    assert report["metrics"]["critical_path_seconds"] == 8
    assert report["quality"] == "partial"
    assert report["provenance"]["artifacts"][0]["uri"] == "raw.json"

def test_top_n_and_pagination_are_deterministic_with_ties():
    rows = [{"name": "b", "duration": 2}, {"name": "a", "duration": 2}, {"name": "c", "duration": 1}]
    assert [row["name"] for row in top_n(rows, "duration", 2)] == ["a", "b"]
    assert paginate(rows, page=2, page_size=2) == [{"name": "c", "duration": 1}]

def test_all_renderers_derive_from_same_report_and_png_is_repeatable():
    report = build_report({"status": "success", "metrics": {"wall_clock_seconds": 3}, "artifacts": []})
    summary = render_job_summary(report)
    first = render_png(report)
    second = render_png(report)
    assert "wall_clock_seconds" in summary
    assert first == second
    assert base64.b64decode(first).startswith(b"\x89PNG\r\n\x1a\n")
