import json

from pipeline_toolkit.trend.service import compare_metric


def _manifest(tag, sha, samples):
    from pipeline_toolkit.trend.model import ReleaseTrendManifest, TrendMetric, TrendRelease, TrendRun
    return ReleaseTrendManifest(TrendRelease("repo", tag, sha * 40, "sha256:" + "d" * 64), TrendRun(f"run-{tag}", "success", "staging", "suite", "config", "runner", "0.1", "https://example.com/a"), (TrendMetric("pipeline.wall_clock", "seconds", samples),))


def test_renderer_preserves_evidence_in_all_text_formats():
    from pipeline_toolkit.trend.render import render_html, render_job_summary, render_json, render_markdown
    result = compare_metric((_manifest("v1.3.0", "c", (10.0, 11.0)), _manifest("v1.4.0", "d", (8.0, 9.0))), "v1.4.0", "previous", "pipeline.wall_clock")
    assert json.loads(render_json(result))["baseline_strategy"] == "previous"
    assert "v1.3.0" in render_markdown(result) and "improved" in render_markdown(result)
    assert "v1.4.0" in render_html(result)
    assert "Baseline strategy" in render_job_summary(result)


def test_inconclusive_renderer_names_reason_without_improvement_claim():
    from pipeline_toolkit.trend.render import render_markdown
    output = render_markdown({"status": "inconclusive", "reason": "environment_mismatch", "baseline_strategy": "explicit"})
    assert "environment_mismatch" in output and "improved" not in output
