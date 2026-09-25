import json

from pipeline_toolkit.cli import main


def _write(root, tag, sha, *, environment="staging", status="success", samples=(10, 11)):
    directory = root / f"{tag}-{environment}"
    directory.mkdir()
    (directory / "trend-manifest.json").write_text(json.dumps({"schema_version": "1.0", "release": {"repository": "repo", "tag": tag, "commit_sha": sha * 40, "image_digest": "sha256:" + "d" * 64}, "run": {"run_id": f"{tag}-{environment}", "status": status, "environment": environment, "suite": "suite", "config_hash": "config", "runner_profile": "runner", "toolkit_version": "0.1", "artifact_uri": "https://example.com/artifact"}, "metrics": [{"id": "pipeline.wall_clock", "unit": "seconds", "samples": samples}]}))


def test_release_trend_cli_handles_previous_explicit_incompatible_and_history(tmp_path, capsys):
    _write(tmp_path, "v1.2.0", "a", samples=(10, 11))
    _write(tmp_path, "v1.3.0", "b", status="failed", samples=())
    _write(tmp_path, "v1.3.1", "c", environment="production", samples=(9, 10))
    _write(tmp_path, "v1.4.0", "d", samples=(8, 9))
    assert main(["trend", "compare", "--history-root", str(tmp_path), "--candidate", "v1.4.0", "--baseline", "previous", "--metric", "pipeline.wall_clock", "--format", "markdown"]) == 0
    assert "v1.2.0" in capsys.readouterr().out
    assert main(["trend", "compare", "--history-root", str(tmp_path), "--candidate", "v1.4.0", "--baseline", "v1.3.1", "--metric", "pipeline.wall_clock", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "environment_mismatch"
    assert main(["trend", "history", "--history-root", str(tmp_path), "--candidate", "v1.4.0", "--metric", "pipeline.wall_clock", "--last", "5", "--format", "job-summary"]) == 0
    assert "v1.4.0" in capsys.readouterr().out
