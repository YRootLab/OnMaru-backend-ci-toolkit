from pathlib import Path


def test_reusable_benchmark_materializes_local_history_and_uploads_trend_report():
    text = Path(".github/workflows/reusable-benchmark.yml").read_text()
    assert "toolkit-ref" in text
    assert "candidate-artifact-name" in text
    assert "history-release-tags" in text
    assert "actions/download-artifact@v4" in text
    assert "gh release download" in text
    assert "trend-manifest.json" in text
    assert "pipeline-toolkit trend compare" in text
    assert "pipeline-toolkit-trend-report" in text
    assert "permissions:" in text and "contents: read" in text
    assert "secrets." not in text


def test_reusable_benchmark_does_not_skip_when_the_caller_was_triggered_by_push_or_dispatch():
    text = Path(".github/workflows/reusable-benchmark.yml").read_text()
    assert "github.event_name == 'workflow_call'" not in text
