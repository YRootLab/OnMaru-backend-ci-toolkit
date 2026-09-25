import json

from pipeline_toolkit.cli import main


def _write(root, tag, sha, samples):
    directory = root / tag
    directory.mkdir()
    path = directory / "trend-manifest.json"
    path.write_text(json.dumps({"schema_version": "1.0", "release": {"repository": "repo", "tag": tag, "commit_sha": sha * 40, "image_digest": "sha256:" + "d" * 64}, "run": {"run_id": tag, "status": "success", "environment": "staging", "suite": "suite", "config_hash": "config", "runner_profile": "runner", "toolkit_version": "0.1", "artifact_uri": "https://example.com/artifact"}, "metrics": [{"id": "pipeline.wall_clock", "unit": "seconds", "samples": samples}]}))


def test_trend_compare_and_history_read_only_local_history(tmp_path, capsys):
    _write(tmp_path, "v1.3.0", "a", [10, 11]); _write(tmp_path, "v1.4.0", "b", [8, 9])
    assert main(["trend", "compare", "--history-root", str(tmp_path), "--candidate", "v1.4.0", "--baseline", "previous", "--metric", "pipeline.wall_clock", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "improved"
    assert main(["trend", "history", "--history-root", str(tmp_path), "--candidate", "v1.4.0", "--metric", "pipeline.wall_clock", "--last", "2", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["candidate"] == "v1.4.0"
