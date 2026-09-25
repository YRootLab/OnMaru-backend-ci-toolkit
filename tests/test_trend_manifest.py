import json
from pathlib import Path

import pytest

from pipeline_toolkit.trend.manifest import discover_manifests, load_manifest


def valid_manifest(**overrides):
    value = {
        "schema_version": "1.0",
        "release": {"repository": "YRootLab/OnMaru-backend", "tag": "v1.2.0", "commit_sha": "a" * 40, "image_digest": "sha256:" + "b" * 64},
        "run": {"run_id": "run-12", "status": "success", "environment": "staging", "suite": "default", "config_hash": "sha256:config", "runner_profile": "ubuntu-amd64-warm", "toolkit_version": "0.1.0", "artifact_uri": "https://github.com/YRootLab/OnMaru-backend/actions/runs/12"},
        "metrics": [{"id": "pipeline.wall_clock", "unit": "seconds", "samples": [12.0, 11.0]}],
    }
    value.update(overrides)
    return value


def write_manifest(path: Path, **overrides):
    path.write_text(json.dumps(valid_manifest(**overrides)))


def test_load_manifest_parses_immutable_release_and_metrics(tmp_path):
    path = tmp_path / "manifest.json"; write_manifest(path)
    manifest = load_manifest(path)
    assert manifest.release.tag == "v1.2.0"
    assert manifest.metrics[0].samples == (12.0, 11.0)
    assert manifest.performance_eligible is True


@pytest.mark.parametrize("path,value,error", [
    ("release", {"repository": "repo", "tag": "v1", "commit_sha": "a" * 40, "image_digest": ""}, "image_digest"),
    ("run", {"run_id": "r", "status": "success", "environment": "e", "suite": "s", "config_hash": "c", "runner_profile": "p", "toolkit_version": "1", "artifact_uri": "https://token@example.com/x"}, "credentials"),
])
def test_load_manifest_rejects_incomplete_identity_and_credential_uri(tmp_path, path, value, error):
    item = valid_manifest(); item[path] = value
    source = tmp_path / "manifest.json"; source.write_text(json.dumps(item))
    with pytest.raises(ValueError, match=error): load_manifest(source)


def test_load_manifest_rejects_non_immutable_sha_and_sensitive_query(tmp_path):
    item = valid_manifest(); item["release"]["commit_sha"] = "not-a-commit"
    source = tmp_path / "manifest.json"; source.write_text(json.dumps(item))
    with pytest.raises(ValueError, match="commit_sha"): load_manifest(source)
    item = valid_manifest(); item["run"]["artifact_uri"] += "?access_token=secret"
    source.write_text(json.dumps(item))
    with pytest.raises(ValueError, match="credentials"): load_manifest(source)


def test_load_manifest_rejects_duplicate_metric_and_non_finite_sample(tmp_path):
    item = valid_manifest(metrics=[{"id": "metric", "unit": "seconds", "samples": [1]}, {"id": "metric", "unit": "seconds", "samples": [2]}])
    path = tmp_path / "duplicate.json"; path.write_text(json.dumps(item))
    with pytest.raises(ValueError, match="duplicate"): load_manifest(path)
    item = valid_manifest(metrics=[{"id": "metric", "unit": "seconds", "samples": [float("nan")]}])
    path.write_text(json.dumps(item))
    with pytest.raises(ValueError, match="finite"): load_manifest(path)


def test_discover_manifests_returns_path_sorted_records(tmp_path):
    (tmp_path / "z").mkdir(); (tmp_path / "a").mkdir()
    write_manifest(tmp_path / "z" / "manifest.json")
    second = valid_manifest(); second["release"]["tag"] = "v1.1.0"; second["release"]["commit_sha"] = "c" * 40
    (tmp_path / "a" / "manifest.json").write_text(json.dumps(second))
    assert [item.release.tag for item in discover_manifests(tmp_path)] == ["v1.1.0", "v1.2.0"]


def test_failed_manifest_is_visible_but_not_performance_eligible(tmp_path):
    item = valid_manifest(); item["run"]["status"] = "failed"; item["metrics"][0]["samples"] = []
    path = tmp_path / "failed.json"; path.write_text(json.dumps(item))
    assert load_manifest(path).performance_eligible is False
