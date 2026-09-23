from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0"

class Quality(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    PARTIAL = "partial"
    MISSING = "missing"
    INVALID = "invalid"
    INCONCLUSIVE = "inconclusive"

@dataclass(frozen=True)
class Artifact:
    uri: str
    sha256: str
    kind: str
    size_bytes: int | None = None
    schema_version: str = SCHEMA_VERSION

@dataclass(frozen=True)
class Evidence:
    benchmark_id: str
    value: float | None
    unit: str
    quality: Quality
    source: str
    source_version: str | None = None
    repository: str | None = None
    commit_sha: str | None = None
    workflow: str | None = None
    job: str | None = None
    raw_artifact: Artifact | None = None
    warnings: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

@dataclass(frozen=True)
class Release:
    repository: str
    tag: str
    commit_sha: str
    image_digest: str
    schema_version: str = SCHEMA_VERSION

@dataclass(frozen=True)
class Deployment:
    environment: str
    release_tag: str
    image_digest: str
    deployed_at: str
    schema_version: str = SCHEMA_VERSION

@dataclass(frozen=True)
class BenchmarkRun:
    run_id: str
    release: Release
    environment: str
    suite: str
    config_hash: str
    runner_profile: str
    artifacts: tuple[Artifact, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    schema_version: str = SCHEMA_VERSION

@dataclass(frozen=True)
class Comparison:
    comparison_id: str
    baseline_release: Release | None
    candidate_release: Release
    run_ids: tuple[str, ...]
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

def _plain(value: Any) -> Any:
    if isinstance(value, Enum): return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, tuple): return [_plain(v) for v in value]
    if isinstance(value, list): return [_plain(v) for v in value]
    if isinstance(value, dict): return {k: _plain(v) for k, v in value.items()}
    return value

def validate(record: Any) -> None:
    if not hasattr(record, "schema_version"):
        raise ValueError("record has no schema_version")
    if record.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {record.schema_version}")
    if isinstance(record, Release):
        for name in ("repository", "tag", "commit_sha", "image_digest"):
            if not getattr(record, name): raise ValueError(f"release.{name} is required")
    elif isinstance(record, Deployment):
        if not all((record.environment, record.release_tag, record.image_digest, record.deployed_at)):
            raise ValueError("incomplete deployment")
        if not record.image_digest.startswith("sha256:"): raise ValueError("deployment.image_digest must be sha256")
    elif isinstance(record, Artifact):
        if not record.uri or not record.sha256 or not record.kind: raise ValueError("incomplete artifact")
    elif isinstance(record, Evidence):
        if not record.benchmark_id or not record.unit or not record.source: raise ValueError("incomplete evidence")
        if record.quality == Quality.SUCCESS and record.value is None: raise ValueError("success evidence requires value")
    elif isinstance(record, BenchmarkRun):
        validate(record.release)
        if not all((record.run_id, record.environment, record.suite, record.config_hash, record.runner_profile)):
            raise ValueError("incomplete benchmark run")
        for item in (*record.artifacts, *record.evidence): validate(item)
    elif isinstance(record, Comparison):
        validate(record.candidate_release)
        if record.baseline_release: validate(record.baseline_release)
        if not record.run_ids: raise ValueError("comparison requires run_ids")

def to_dict(record: Any) -> dict[str, Any]:
    validate(record)
    return _plain(record)
