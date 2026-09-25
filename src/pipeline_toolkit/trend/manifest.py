from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse

from .model import ReleaseTrendManifest, TrendMetric, TrendRelease, TrendRun

_STATUSES = {"success", "failed", "cancelled", "timeout", "partial", "missing", "invalid", "inconclusive"}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def _mapping(value: object, field: str) -> dict:
    if not isinstance(value, dict): raise ValueError(f"{field} must be an object")
    return value


def _artifact_uri(value: object) -> str:
    uri = _text(value, "run.artifact_uri")
    parsed = urlparse(uri)
    if parsed.username or parsed.password or re.search(r"(?:access[_-]?token|api[_-]?key|password|secret)=", parsed.query, re.I):
        raise ValueError("run.artifact_uri must not contain credentials")
    if parsed.scheme not in {"https", "artifact", "s3", "gs", "file"}: raise ValueError("run.artifact_uri has unsupported scheme")
    if parsed.scheme == "file" and not parsed.path: raise ValueError("run.artifact_uri file URI requires a path")
    if parsed.scheme != "file" and not parsed.netloc: raise ValueError("run.artifact_uri requires an authority")
    return uri


def load_manifest(path: Path) -> ReleaseTrendManifest:
    try: document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"invalid manifest: {path}") from exc
    document = _mapping(document, "manifest")
    if document.get("schema_version") != "1.0": raise ValueError("unsupported schema_version")
    release_data = _mapping(document.get("release"), "release")
    release = TrendRelease(*[_text(release_data.get(key), f"release.{key}") for key in ("repository", "tag", "commit_sha", "image_digest")])
    if not re.fullmatch(r"[0-9a-f]{40}", release.commit_sha): raise ValueError("release.commit_sha must be 40 lowercase hexadecimal characters")
    if not release.image_digest.startswith("sha256:"): raise ValueError("release.image_digest must be sha256")
    run_data = _mapping(document.get("run"), "run")
    status = _text(run_data.get("status"), "run.status")
    if status not in _STATUSES: raise ValueError("unsupported run.status")
    run = TrendRun(_text(run_data.get("run_id"), "run.run_id"), status, *[_text(run_data.get(key), f"run.{key}") for key in ("environment", "suite", "config_hash", "runner_profile", "toolkit_version")], _artifact_uri(run_data.get("artifact_uri")))
    metrics_data = document.get("metrics")
    if not isinstance(metrics_data, list) or not metrics_data: raise ValueError("metrics must be a non-empty array")
    metrics, seen = [], set()
    for raw in metrics_data:
        raw = _mapping(raw, "metric"); metric_id = _text(raw.get("id"), "metric.id")
        if metric_id in seen: raise ValueError("duplicate metric id")
        seen.add(metric_id); samples = raw.get("samples")
        if not isinstance(samples, list): raise ValueError("metric.samples must be an array")
        values = tuple(float(value) for value in samples)
        if not all(math.isfinite(value) for value in values): raise ValueError("metric.samples must be finite")
        metrics.append(TrendMetric(metric_id, _text(raw.get("unit"), "metric.unit"), values))
    return ReleaseTrendManifest(release, run, tuple(metrics))


def discover_manifests(history_root: Path) -> tuple[ReleaseTrendManifest, ...]:
    if not history_root.is_dir(): raise ValueError("history_root must be an existing directory")
    return tuple(load_manifest(path) for path in sorted(history_root.rglob("trend-manifest.json")) if path.is_file())
