import json
import subprocess
from pathlib import Path
from pipeline_toolkit.cli import main


def write_valid_bundle(tmp_path):
    source = tmp_path / "facts.json"
    source.write_text(json.dumps({
        "title": "CI observation",
        "observed_at": "2026-09-24",
        "summary": "Measured the automatic checks before merging code.",
        "facts": [{
            "name": "serial CI",
            "value": 454,
            "unit": "seconds",
            "status": "success",
            "source_url": "https://github.com/example/repo/actions/runs/1",
            "comparable": True,
        }],
        "limitations": ["Three same-commit samples are still needed."],
        "next_steps": ["Collect comparable samples."],
    }), encoding="utf-8")
    return source

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


def test_report_bundle_is_dry_run_by_default(tmp_path, capsys):
    source = write_valid_bundle(tmp_path)

    assert main([
        "report-bundle", "--input", str(source), "--slug", "ci", "--repo-root", str(tmp_path),
    ]) == 0

    assert not (tmp_path / "docs/reports/2026-09-24-ci-detailed.md").exists()
    summary = json.loads(capsys.readouterr().out)
    assert summary["dry_run"] is True
    assert summary["audiences"] == ["developer", "easy"]
    assert summary["ai_requested"] is False
    assert summary["planned_paths"] == [
        "docs/reports/2026-09-24-ci-detailed.md",
        "docs/reports/easy/2026-09-24-ci-easy.md",
        "docs/reports/easy/prompts/generated/2026-09-24-ci-easy-prompt.md",
        "docs/reports/prompts/generated/2026-09-24-ci-detailed-prompt.md",
    ]


def test_report_bundle_requires_write_for_overwrite_and_provider_model_pair(tmp_path):
    source = write_valid_bundle(tmp_path)

    assert main(["report-bundle", "--input", str(source), "--slug", "ci", "--overwrite"]) == 2
    assert main(["report-bundle", "--input", str(source), "--slug", "ci", "--ai-provider", "openai"]) == 2
    assert main(["report-bundle", "--input", str(source), "--slug", "ci", "--model", "gpt-5"]) == 2
    assert main([
        "report-bundle", "--input", str(source), "--slug", "ci", "--ai-provider", "openai", "--model", "gpt-5",
    ]) == 2


def test_report_bundle_writes_selected_audience_only(tmp_path, capsys):
    source = write_valid_bundle(tmp_path)

    assert main([
        "report-bundle", "--input", str(source), "--slug", "ci", "--audience", "developer",
        "--repo-root", str(tmp_path), "--write",
    ]) == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["dry_run"] is False
    assert summary["audiences"] == ["developer"]
    assert (tmp_path / "docs/reports/2026-09-24-ci-detailed.md").exists()
    assert not (tmp_path / "docs/reports/easy/2026-09-24-ci-easy.md").exists()


def test_report_bundle_end_to_end_writes_both_audiences_and_keeps_easy_ignored(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures/report_bundle/ci-observation.json"
    source = tmp_path / "facts.json"
    source.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".gitignore").write_text("docs/reports/easy/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    assert main([
        "report-bundle", "--input", str(source), "--slug", "ci-smoke", "--repo-root", str(tmp_path),
        "--audience", "both", "--write",
    ]) == 0

    summary = json.loads(capsys.readouterr().out)
    developer = tmp_path / "docs/reports/2026-09-25-ci-smoke-detailed.md"
    easy = tmp_path / "docs/reports/easy/2026-09-25-ci-smoke-easy.md"
    assert summary["dry_run"] is False
    assert developer.exists() and easy.exists()
    assert "개선 성과로 사용하지 않음" in easy.read_text(encoding="utf-8")
    assert subprocess.run(
        ["git", "check-ignore", "-q", str(easy.relative_to(tmp_path))], cwd=tmp_path
    ).returncode == 0
