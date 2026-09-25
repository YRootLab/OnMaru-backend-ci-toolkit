from pathlib import Path


def test_reusable_benchmark_materializes_local_history_and_uploads_trend_report():
    text = Path(".github/workflows/reusable-benchmark.yml").read_text()
    assert "history-root" in text
    assert "python -m pipeline_toolkit.cli trend compare" in text
    assert "pipeline-toolkit-trend-report" in text
    assert "permissions:" in text and "contents: read" in text
    assert "secrets." not in text
