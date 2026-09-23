import json
from pipeline_toolkit.cli import main

def test_cli_version_is_machine_readable(capsys):
    assert main(["version"]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == "0.1.0"

def test_cli_compare_emits_inconclusive_for_missing_baseline(tmp_path, capsys):
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({"samples": [1, 2]}))
    assert main(["compare", "--candidate", str(candidate)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "inconclusive"

def test_cli_report_writes_deterministic_markdown(tmp_path):
    source = tmp_path / "report.json"
    output = tmp_path / "report.md"
    source.write_text(json.dumps({"status": "success", "metrics": {"wall_clock_seconds": 2}, "artifacts": []}))
    assert main(["report", "--input", str(source), "--format", "markdown", "--output", str(output)]) == 0
    assert "# Benchmark report" in output.read_text()
