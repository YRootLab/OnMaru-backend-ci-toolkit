from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrendRelease:
    repository: str
    tag: str
    commit_sha: str
    image_digest: str


@dataclass(frozen=True)
class TrendRun:
    run_id: str
    status: str
    environment: str
    suite: str
    config_hash: str
    runner_profile: str
    toolkit_version: str
    artifact_uri: str


@dataclass(frozen=True)
class TrendMetric:
    id: str
    unit: str
    samples: tuple[float, ...]


@dataclass(frozen=True)
class ReleaseTrendManifest:
    release: TrendRelease
    run: TrendRun
    metrics: tuple[TrendMetric, ...]
    schema_version: str = "1.0"

    @property
    def performance_eligible(self) -> bool:
        return self.run.status == "success" and any(metric.samples for metric in self.metrics)
